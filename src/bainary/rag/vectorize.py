# mypy: ignore-errors
"""Textual vectorizer: deterministic text → float[] for similarity search.

No embedding model, no network, no API key. Uses the **hashing trick** over
n-gram tokens of the function text. Same text always produces the same vector;
the resulting corpus can be compared with cosine similarity (the existing
`VectorStore.search`).

Public API:

    TextualVectorizer (ABC)
        └── HashingTextVectorizer (default, offline, no deps)

    create_textual_vectorizer() -> TextualVectorizer
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod

from bainary.rag.errors import RagError

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|\d+|==|!=|<=|>=|->|<<|>>|[{}()\[\];,.]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def _ngrams(tokens: list[str], n: int) -> list[str]:
    if not tokens:
        return []
    if len(tokens) < n:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


class TextualVectorizer(ABC):
    """Convert a list of texts to fixed-dim float vectors."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """Dimensionality of the produced vectors."""

    @abstractmethod
    def vectorize(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per text. Same text → same vector.

        Raises
        ------
        RagError
            If vectorization fails.
        """


class HashingTextVectorizer(TextualVectorizer):
    """Hashing-trick vectorizer over character-n-gram tokens.

    For each text:
      1. Tokenize (C-like tokens + operators).
      2. Generate 1- and 2-grams.
      3. Hash each n-gram to a bucket in [0, dim).
      4. Apply a sub-linear TF weight (1 + log(count)) and L2-normalize.

    No state, no model, no API key, deterministic, fast.
    """

    def __init__(self, dim: int = 1024, ngram_range: tuple[int, int] = (1, 2)) -> None:
        if dim <= 0:
            raise RagError("HashingTextVectorizer requires dim > 0")
        if not (1 <= ngram_range[0] <= ngram_range[1]):
            raise RagError("ngram_range must satisfy 1 <= min <= max")
        self._dim = dim
        self._ngram_range = ngram_range

    @property
    def dim(self) -> int:
        return self._dim

    def vectorize(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        out: list[list[float]] = []
        for text in texts:
            tokens = _tokenize(text)
            counts: dict[int, float] = {}
            for n in range(self._ngram_range[0], self._ngram_range[1] + 1):
                for ng in _ngrams(tokens, n):
                    h = hashlib.blake2b(ng.encode("utf-8"), digest_size=8).digest()
                    bucket = int.from_bytes(h, "little") % self._dim
                    counts[bucket] = counts.get(bucket, 0.0) + 1.0
            if not counts:
                out.append([0.0] * self._dim)
                continue
            # Sub-linear TF weight (like scikit-learn's HashingVectorizer default).
            vec = np.zeros(self._dim, dtype=float)
            for bucket, c in counts.items():
                vec[bucket] = 1.0 + float(np.log(c))
            n = float(np.linalg.norm(vec))
            if n > 0:
                vec /= n
            out.append([float(x) for x in vec])
        return out


def create_textual_vectorizer() -> TextualVectorizer:
    """Factory: returns the default `HashingTextVectorizer`."""
    return HashingTextVectorizer()
