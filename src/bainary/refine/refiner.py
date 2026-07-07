# mypy: ignore-errors
"""Refiner: orchestrates LLM refinement of decompiled pseudo-C."""

from __future__ import annotations

import copy
import hashlib
import logging
import re

from bainary.graph import CallGraph
from bainary.lift.artifact import BinaryArtifact, Function
from bainary.refine.cache import RefinementCache
from bainary.refine.client import LLMClient
from bainary.refine.errors import RefineError
from bainary.refine.prompts import PROMPT_VERSION, build_prompt

log = logging.getLogger(__name__)


def _strip_markdown_fences(content: str) -> str:
    """Extract code from markdown code fences."""
    content = content.strip()
    open_match = re.search(r"^```[a-zA-Z0-9_+-]*\s*$", content, re.MULTILINE)
    if open_match is not None:
        after_open = content[open_match.end() :]
        close_match = re.search(r"^```\s*$", after_open, re.MULTILINE)
        if close_match is not None:
            content = after_open[: close_match.start()]
        else:
            content = after_open
    else:
        content = re.sub(r"\n*```\s*$", "", content)
    return content.strip()


def _cache_key(pseudo_c: str, model: str) -> str:
    """Compute the cache key for a function's pseudo-C."""
    raw = f"{pseudo_c}:{model}:{PROMPT_VERSION}"
    return hashlib.sha256(raw.encode()).hexdigest()


class Refiner:
    """Refines decompiled pseudo-C using an LLM.

    Takes a BinaryArtifact (from A) and optionally a CallGraph (from B),
    sends each function's pseudo-C to an LLM for refinement, and returns
    a new BinaryArtifact with the refined pseudo-C.

    The original artifact is never modified.
    """

    def __init__(
        self,
        client: LLMClient,
        cache: RefinementCache | None = None,
        *,
        min_size: int = 0,
        skip_thunks: bool = True,
        skip_no_pseudocode: bool = True,
    ) -> None:
        self._client = client
        self._cache = cache or RefinementCache(model=client.model_name)
        self._min_size = min_size
        self._skip_thunks = skip_thunks
        self._skip_no_pseudocode = skip_no_pseudocode

    def refine(
        self,
        artifact: BinaryArtifact,
        cg: CallGraph | None = None,
        *,
        min_size: int | None = None,
        skip_thunks: bool | None = None,
        skip_no_pseudocode: bool | None = None,
    ) -> BinaryArtifact:
        """Refine pseudo-C for all eligible functions.

        Returns a new BinaryArtifact; the original is not modified.
        """
        min_size = min_size if min_size is not None else self._min_size
        skip_thunks = skip_thunks if skip_thunks is not None else self._skip_thunks
        skip_no_pseudocode = (
            skip_no_pseudocode if skip_no_pseudocode is not None else self._skip_no_pseudocode
        )

        # Deep-copy the artifact so the original is never touched
        refined = copy.deepcopy(artifact)

        for fn in refined.functions:
            refined_code, error = self._refine_one(
                fn, cg, min_size, skip_thunks, skip_no_pseudocode
            )
            if refined_code is not None:
                fn.pseudocode = refined_code
            elif error is not None:
                # LLM call failed or returned empty; record the reason on the
                # deep-copy's function (the original artifact is untouched).
                fn.pseudocode_error = error
        return refined

    def refine_one(
        self,
        fn: Function,
        cg: CallGraph | None = None,
        *,
        min_size: int | None = None,
        skip_thunks: bool | None = None,
        skip_no_pseudocode: bool | None = None,
    ) -> str | None:
        """Refine a single function's pseudo-C and return the refined code.

        Returns the refined code string, or ``None`` when the function is
        filtered out (skip_thunks, skip_no_pseudocode, min_size), has no
        pseudocode, the LLM call fails, or the LLM returns an empty response.

        Uses the same cache, filters, and prompt logic as :meth:`refine`.
        The original ``fn`` is never modified.
        """
        refined_code, _error = self._refine_one(
            fn,
            cg,
            min_size if min_size is not None else self._min_size,
            skip_thunks if skip_thunks is not None else self._skip_thunks,
            skip_no_pseudocode if skip_no_pseudocode is not None else self._skip_no_pseudocode,
        )
        return refined_code

    def _refine_one(
        self,
        fn: Function,
        cg: CallGraph | None,
        min_size: int,
        skip_thunks: bool,
        skip_no_pseudocode: bool,
    ) -> tuple[str | None, str | None]:
        """Internal single-function refinement.

        Returns ``(refined_code, error)`` where exactly one is non-None when
        the LLM was invoked, and both are ``None`` when the function was
        filtered out (no LLM call attempted).

        Contract: ``fn`` is never mutated by this helper. The caller
        (:meth:`refine` or :meth:`refine_one`) owns any mutation of fn.
        """
        if not fn.pseudocode:
            return None, None
        # skip_no_pseudocode is already covered by the early-return above
        # (we never reach here when there's no pseudocode), but kept for
        # symmetry with the original filter sequence.
        _ = skip_no_pseudocode
        if skip_thunks and fn.is_thunk:
            return None, None
        if min_size > 0 and fn.size_bytes < min_size:
            return None, None

        caller_names: list[str] = []
        callee_names: list[str] = []
        if cg is not None:
            try:
                caller_names = sorted(cg.callers_of(fn.name))
            except Exception:
                pass
            try:
                callee_names = sorted(cg.callees_of(fn.name))
            except Exception:
                pass

        key = _cache_key(fn.pseudocode, self._client.model_name)
        cached = self._cache.lookup(key)
        if cached is not None:
            return cached, None

        prompt = build_prompt(
            function_name=fn.name,
            pseudo_c=fn.pseudocode,
            caller_names=caller_names or None,
            callee_names=callee_names or None,
        )

        try:
            raw_response = self._client.complete(prompt)
            refined_code = _strip_markdown_fences(raw_response)
            if not refined_code:
                return None, "LLM returned empty response"
            self._cache.store(key, refined_code)
            return refined_code, None
        except RefineError as e:
            return None, str(e)
