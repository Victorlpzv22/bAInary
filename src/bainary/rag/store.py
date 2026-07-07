# mypy: ignore-errors
"""Vector store backends for the RAG subsystem.

Pluggable persistence for function embedding vectors + metadata.
MVP: InMemoryStore (numpy-backed) + NumpyFileStore (numpy + JSON dump).
Future backends (ChromaDB / LanceDB / FAISS / sqlite-vec) implement
the same VectorStore ABC without touching consumers.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
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


class NumpyFileStore(VectorStore):
    """Persistent vector store backed by numpy + JSON.

    Layout:
        <root>/store.npy      — float32 matrix of shape (n, dim)
        <root>/records.json  — list of VectorRecord dicts

    On load, if either file is missing/corrupt, the store starts empty
    (with a warning in the log) so a corrupt cache never crashes the user.
    """

    def __init__(self, root: Path | None = None, *, dim: int = 0) -> None:
        if root is None:
            root = Path.home() / ".cache" / "bainary" / "rag"
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._vectors_path = self._root / "store.npy"
        self._records_path = self._root / "records.json"
        self._records: dict[str, VectorRecord] = {}
        self._dim = dim
        self._load()
        if self._dim == 0 and self._records:
            first = next(iter(self._records.values()))
            self._dim = len(first.vector)

    @property
    def dim(self) -> int:
        return self._dim

    def _load(self) -> None:
        if not self._records_path.exists() or not self._vectors_path.exists():
            return
        try:
            records_raw = json.loads(self._records_path.read_text())
            import numpy as np

            matrix = np.load(self._vectors_path)  # type: ignore[arg-type]
            if matrix.ndim != 2 or matrix.shape[0] != len(records_raw):
                log.warning("rag store.npy shape mismatch; starting empty")
                self._records = {}
                return
            for rd in records_raw:
                rec = VectorRecord.from_dict(rd)
                if len(rec.vector) != matrix.shape[1]:
                    log.warning("rag store dim mismatch; starting empty")
                    self._records = {}
                    return
                self._records[rec.id] = rec
        except (OSError, ValueError, json.JSONDecodeError) as e:
            log.warning("Corrupt RAG store (%s); starting empty", e)
            self._records = {}

    def _write(self) -> None:
        import numpy as np

        if not self._records:
            matrix = np.zeros((0, max(self._dim, 1)), dtype="float32")
        else:
            rows = [list(r.vector) for r in self._records.values()]
            matrix = np.asarray(rows, dtype="float32")
        np.save(self._vectors_path, matrix)
        self._records_path.write_text(
            json.dumps([r.to_dict() for r in self._records.values()], indent=2)
        )

    def upsert(self, records: list[VectorRecord]) -> None:
        for r in records:
            if self._dim == 0:
                self._dim = len(r.vector)
            if len(r.vector) != self._dim:
                raise RagError(f"vector dim mismatch: expected {self._dim}, got {len(r.vector)}")
            self._records[r.id] = r

    def get(self, id: str) -> VectorRecord | None:
        return self._records.get(id)

    def search(self, vector: list[float], k: int) -> list[SearchHit]:
        if not self._records:
            return []
        scored = [(_cosine_similarity(vector, r.vector), r) for r in self._records.values()]
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
        if to_remove:
            self._write()
        return len(to_remove)

    def count(self) -> int:
        return len(self._records)

    def flush(self) -> None:
        self._write()

    def close(self) -> None:
        self._write()
