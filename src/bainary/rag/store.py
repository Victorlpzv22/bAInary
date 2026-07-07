# mypy: ignore-errors
"""Vector store backends for the RAG subsystem.

Pluggable persistence for function embedding vectors + metadata.
MVP: InMemoryStore (numpy-backed) + NumpyFileStore (numpy + JSON dump).
Future backends (ChromaDB / LanceDB / FAISS / sqlite-vec) implement
the same VectorStore ABC without touching consumers.
"""

from __future__ import annotations

import json  # noqa: F401  (used in Task 5 NumpyFileStore)
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path  # noqa: F401  (used in Task 5 NumpyFileStore)
from typing import Any

from bainary.lift.artifact import Function
from bainary.rag.errors import RagError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchHit:
    function: Function
    binary_sha256: str
    score: float
    source: str


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    function: dict[str, Any]
    binary_sha256: str
    name: str
    address: str
    source: str
    text_hash: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VectorRecord:
        return cls(
            id=d["id"],
            vector=list(d["vector"]),
            function=d["function"],
            binary_sha256=d["binary_sha256"],
            name=d["name"],
            address=d["address"],
            source=d["source"],
            text_hash=d["text_hash"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "vector": list(self.vector),
            "function": self.function,
            "binary_sha256": self.binary_sha256,
            "name": self.name,
            "address": self.address,
            "source": self.source,
            "text_hash": self.text_hash,
        }


class VectorStore(ABC):
    """Abstract interface for a vector store with metadata."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """The dimensionality of stored vectors."""

    @abstractmethod
    def upsert(self, records: list[VectorRecord]) -> None:
        """Insert or replace records by `id`. Same `id` overwrites."""

    @abstractmethod
    def get(self, id: str) -> VectorRecord | None:
        """Fetch a single record by id, or None if missing."""

    @abstractmethod
    def search(self, vector: list[float], k: int) -> list[SearchHit]:
        """Return the top-k nearest records by cosine similarity."""

    @abstractmethod
    def remove_binary(self, binary_sha256: str) -> int:
        """Remove all records belonging to the given binary. Returns count removed."""

    @abstractmethod
    def count(self) -> int:
        """Number of stored records."""

    def flush(self) -> None:  # noqa: B027
        """For persistent stores: write to disk. No-op for in-memory."""

    def close(self) -> None:  # noqa: B027
        """Release any resources. No-op for in-memory."""


def _cosine_similarity(query: list[float], vec: list[float]) -> float:
    """Cosine similarity in [-1, 1]. Zero vectors return 0."""
    import numpy as np

    q = np.asarray(query, dtype=float)
    v = np.asarray(vec, dtype=float)
    qn = float(np.linalg.norm(q))
    vn = float(np.linalg.norm(v))
    if qn == 0 or vn == 0:
        return 0.0
    return float(np.dot(q, v) / (qn * vn))


class InMemoryStore(VectorStore):
    """In-process store backed by a dict; used in tests and short-lived corpora."""

    def __init__(self, dim: int) -> None:
        self._dim = dim
        self._records: dict[str, VectorRecord] = {}

    @property
    def dim(self) -> int:
        return self._dim

    def upsert(self, records: list[VectorRecord]) -> None:
        for r in records:
            if len(r.vector) != self._dim:
                raise RagError(f"vector dim mismatch: expected {self._dim}, got {len(r.vector)}")
            self._records[r.id] = r

    def get(self, id: str) -> VectorRecord | None:
        return self._records.get(id)

    def search(self, vector: list[float], k: int) -> list[SearchHit]:
        if not self._records:
            return []
        scored: list[tuple[float, VectorRecord]] = []
        for r in self._records.values():
            scored.append((_cosine_similarity(vector, r.vector), r))
        scored.sort(key=lambda t: t[0], reverse=True)
        hits: list[SearchHit] = []
        for score, r in scored[:k]:
            hits.append(
                SearchHit(
                    function=Function.from_dict(r.function),
                    binary_sha256=r.binary_sha256,
                    score=score,
                    source=r.source,
                )
            )
        return hits

    def remove_binary(self, binary_sha256: str) -> int:
        to_remove = [rid for rid, r in self._records.items() if r.binary_sha256 == binary_sha256]
        for rid in to_remove:
            del self._records[rid]
        return len(to_remove)

    def count(self) -> int:
        return len(self._records)
