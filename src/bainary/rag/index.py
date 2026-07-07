# mypy: ignore-errors
"""Index: cross-binary textual-similarity index of functions.

No embedding model. Each function's text is vectorized locally with a
`TextualVectorizer` (hashing trick by default), the vectors are stored in a
`VectorStore`, and cosine similarity ranks hits.

Public API:

    Index(vectorizer, store=None, *, skip_no_text=True)
        .add_artifact(artifact)
        .search(query, k=5)
        .search_similar(fn, k=5)
        .retrieve_context(fn, k=5)
        .remove_artifact(binary_sha256)
        .flush() / .close()
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from bainary.lift.artifact import BinaryArtifact, Function
from bainary.rag.errors import RagError
from bainary.rag.store import NumpyFileStore, SearchHit, VectorRecord, VectorStore
from bainary.rag.text import build_text
from bainary.rag.vectorize import TextualVectorizer

log = logging.getLogger(__name__)


def _record_id(binary_sha256: str, fn_address: str) -> str:
    return hashlib.sha256(f"{binary_sha256}:{fn_address}".encode()).hexdigest()


class Index:
    """Cross-binary textual-similarity index of functions."""

    def __init__(
        self,
        vectorizer: TextualVectorizer,
        store: VectorStore | None = None,
        *,
        skip_no_text: bool = True,
    ) -> None:
        self._vectorizer = vectorizer
        if store is None:
            store = NumpyFileStore(dim=vectorizer.dim)
        if store.dim != 0 and store.dim != vectorizer.dim:
            raise RagError(f"store dim {store.dim} does not match vectorizer dim {vectorizer.dim}")
        self._store = store
        self._skip_no_text = skip_no_text

    def __len__(self) -> int:
        return self._store.count()

    def add_artifact(self, artifact: BinaryArtifact) -> None:
        """Index every function in `artifact`. Skips functions with empty text
        unless `skip_no_text=False`, in which case it raises RagError.
        """
        records: list[VectorRecord] = []
        for fn in artifact.functions:
            text = build_text(fn)
            if not text:
                if self._skip_no_text:
                    continue
                raise RagError(f"empty text for function {fn.name} at {fn.address}")

            rid = _record_id(artifact.binary.sha256, fn.address)
            existing = self._store.get(rid)
            if existing is not None:
                # Already indexed; the function's address is its identity here.
                # No text-hash cache: vectorization is cheap and local.
                continue

            try:
                vectors = self._vectorizer.vectorize([text])
            except RagError as e:
                log.warning("vectorize failed for one function: %s", e)
                continue
            if not vectors:
                continue
            vector = vectors[0]
            if len(vector) != self._vectorizer.dim:
                raise RagError(
                    f"vectorizer dim mismatch: expected {self._vectorizer.dim}, got {len(vector)}"
                )

            records.append(
                VectorRecord(
                    id=rid,
                    vector=vector,
                    function=fn.to_dict(),
                    binary_sha256=artifact.binary.sha256,
                    name=fn.name,
                    address=fn.address,
                    source=artifact.binary.path,
                    text_hash="",  # unused; kept for back-compat with VectorRecord
                )
            )

        if records:
            self._store.upsert(records)
        self._store.flush()

    def search(self, query: str, k: int = 5) -> list[SearchHit]:
        """Search the corpus with a natural-language query."""
        try:
            vectors = self._vectorizer.vectorize([query])
        except RagError as e:
            log.warning("vectorize failed for query: %s", e)
            return []
        if not vectors:
            return []
        return self._store.search(vectors[0], k)

    def search_similar(self, fn: Function, k: int = 5) -> list[SearchHit]:
        """Find functions similar to a given Function (itself will be the top hit if indexed)."""
        text = build_text(fn)
        try:
            vectors = self._vectorizer.vectorize([text])
        except RagError as e:
            log.warning("vectorize failed for function: %s", e)
            return []
        if not vectors:
            return []
        return self._store.search(vectors[0], k)

    def retrieve_context(self, fn: Function, k: int = 5) -> dict[str, Any]:
        """Structured block for LLM prompt injection (consumed by D later)."""
        hits = self.search_similar(fn, k)
        return {"neighbors": [(h.function, h.score) for h in hits]}

    def remove_artifact(self, binary_sha256: str) -> int:
        """Remove all functions of a binary from the corpus."""
        return self._store.remove_binary(binary_sha256)

    def gc_orphans(self, artifact: BinaryArtifact) -> int:
        """Remove VectorRecords of `artifact.binary.sha256` whose address is not
        present in the current `artifact`. Returns the count removed.

        Idempotent and safe to call after every add_artifact; no-op if no orphans.
        """
        valid_ids = {_record_id(artifact.binary.sha256, fn.address) for fn in artifact.functions}
        removed = 0
        for r in self._store.list_by_binary(artifact.binary.sha256):
            if r.id not in valid_ids:
                if self._store.remove_by_id(r.id):
                    removed += 1
        return removed

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.flush()
        self._store.close()
