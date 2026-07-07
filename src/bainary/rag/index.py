# mypy: ignore-errors
"""Index: the RAG orchestrator combining embeddings, store, and cache."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from bainary.lift.artifact import BinaryArtifact, Function
from bainary.rag.client import EmbeddingClient
from bainary.rag.errors import RagError
from bainary.rag.store import NumpyFileStore, SearchHit, VectorRecord, VectorStore
from bainary.rag.text import TEXT_VERSION, build_text

log = logging.getLogger(__name__)


def _record_id(binary_sha256: str, fn_address: str) -> str:
    return hashlib.sha256(f"{binary_sha256}:{fn_address}".encode()).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _embedding_cache_key(text: str, model: str) -> str:
    return hashlib.sha256(f"{text}:{model}:{TEXT_VERSION}".encode()).hexdigest()


class EmbeddingCache:
    """File-based cache for embedding vectors, keyed by sha256(text+model+TEXT_VERSION)."""

    def __init__(self, root: Path | None = None, *, model: str = "unknown") -> None:
        if root is None:
            root = Path.home() / ".cache" / "bainary" / "rag" / "embeddings"
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._model = model

    def _path_for(self, key: str) -> Path:
        return self._root / key[:2] / key[2:4] / f"{key}.json"

    def lookup(self, key: str) -> list[float] | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Corrupt embedding cache entry %s: %s. Deleting.", path, e)
            try:
                path.unlink()
            except OSError:
                pass
            return None
        if raw.get("model") != self._model:
            return None
        if raw.get("text_version") != TEXT_VERSION:
            return None
        vec = raw.get("vector")
        return list(vec) if vec is not None else None

    def store(self, key: str, vector: list[float]) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "key": key,
            "vector": list(vector),
            "model": self._model,
            "text_version": TEXT_VERSION,
        }
        path.write_text(json.dumps(entry))


class Index:
    """Cross-binary semantic index of functions."""

    def __init__(
        self,
        embeddings: EmbeddingClient,
        store: VectorStore | None = None,
        *,
        embedding_cache_root: Path | None = None,
        skip_no_text: bool = True,
    ) -> None:
        self._embeddings = embeddings
        if store is None:
            store = NumpyFileStore(dim=embeddings.dim)
        if store.dim != 0 and store.dim != embeddings.dim:
            raise RagError(f"store dim {store.dim} does not match embeddings dim {embeddings.dim}")
        self._store = store
        self._cache = EmbeddingCache(embedding_cache_root, model=embeddings.model_name)
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
            thash = _text_hash(text)

            existing = self._store.get(rid)
            if existing is not None and existing.text_hash == thash:
                continue

            vector = self._maybe_embed(text)
            if vector is None:
                continue

            records.append(
                VectorRecord(
                    id=rid,
                    vector=vector,
                    function=fn.to_dict(),
                    binary_sha256=artifact.binary.sha256,
                    name=fn.name,
                    address=fn.address,
                    source=artifact.binary.path,
                    text_hash=thash,
                )
            )

        if records:
            self._store.upsert(records)
        self._store.flush()

    def _maybe_embed(self, text: str) -> list[float] | None:
        """Cached embedding lookup with partial-failure handling."""
        key = _embedding_cache_key(text, self._embeddings.model_name)
        cached = self._cache.lookup(key)
        if cached is not None:
            return cached
        try:
            vectors = self._embeddings.embed([text])
        except RagError as e:
            log.warning("embedding failed for one text: %s", e)
            return None
        if not vectors:
            return None
        vector = vectors[0]
        if len(vector) != self._embeddings.dim:
            raise RagError(
                f"embedding dim mismatch: expected {self._embeddings.dim}, got {len(vector)}"
            )
        self._cache.store(key, vector)
        return vector

    def search(self, query: str, k: int = 5) -> list[SearchHit]:
        """Search the corpus with a natural-language query."""
        vector = self._maybe_embed(query)
        if vector is None:
            return []
        return self._store.search(vector, k)

    def search_similar(self, fn: Function, k: int = 5) -> list[SearchHit]:
        """Find functions similar to a given Function (itself will be the top hit if indexed)."""
        text = build_text(fn)
        vector = self._maybe_embed(text)
        if vector is None:
            return []
        return self._store.search(vector, k)

    def retrieve_context(self, fn: Function, k: int = 5) -> dict[str, Any]:
        """Structured block for LLM prompt injection (consumed by D later)."""
        hits = self.search_similar(fn, k)
        return {"neighbors": [(h.function, h.score) for h in hits]}

    def remove_artifact(self, binary_sha256: str) -> int:
        """Remove all functions of a binary from the corpus."""
        return self._store.remove_binary(binary_sha256)

    def flush(self) -> None:
        self._store.flush()

    def close(self) -> None:
        self._store.flush()
        self._store.close()
