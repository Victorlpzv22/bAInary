# mypy: ignore-errors
"""Refiner: orchestrates LLM refinement of decompiled pseudo-C."""

from __future__ import annotations

import copy
import hashlib
import logging
import re

from bainary.graph import CallGraph
from bainary.lift.artifact import BinaryArtifact
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
            # Apply filters
            if skip_no_pseudocode and not fn.pseudocode:
                continue
            if skip_thunks and fn.is_thunk:
                continue
            if min_size > 0 and fn.size_bytes < min_size:
                continue
            if not fn.pseudocode:
                continue

            # Get call graph context
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

            # Check cache
            key = _cache_key(fn.pseudocode, self._client.model_name)
            cached = self._cache.lookup(key)
            if cached is not None:
                fn.pseudocode = cached
                continue

            # Build prompt and call LLM
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
                    fn.pseudocode_error = "LLM returned empty response"
                    continue
                fn.pseudocode = refined_code
                self._cache.store(key, refined_code)
            except RefineError as e:
                fn.pseudocode_error = str(e)

        return refined
