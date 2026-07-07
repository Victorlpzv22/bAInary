# mypy: ignore-errors
"""Textual vectorizer: deterministic text → float[] for similarity search.

No embedding model, no network, no API key. Two implementations:

  - `HashingTextVectorizer` (default): stateless hashing trick over n-gram
    tokens. Same text → same vector. Drop-in.
  - `TfidfTextVectorizer`: stateful TF-IDF over a learned vocabulary. Higher
    recall for exact matches, with a `fit()` step that builds the vocab
    from a corpus. `save` / `load` roundtrips the state as JSON.

Public API:

    TextualVectorizer (ABC)
        ├── HashingTextVectorizer
        └── TfidfTextVectorizer

    create_textual_vectorizer() -> TextualVectorizer
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from pathlib import Path

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


class TfidfTextVectorizer(TextualVectorizer):
    """TF-IDF vectorizer over n-gram tokens with a learned vocabulary.

    Two-phase use:
      1. `fit(texts)` builds the vocabulary and IDF weights from a corpus.
      2. `vectorize(texts)` returns TF-IDF weighted, L2-normalized vectors.

    State (`_vocab`, `_idf`) is JSON-serializable via `save(path)` /
    `load(path)` so a fitted vectorizer can be reused across sessions
    without re-fitting.

    Parameters
    ----------
    dim : int
        Dimensionality of the output vectors. With more vocabulary tokens
        than `dim`, hashing trick packs multiple tokens into the same
        bucket (collisions are tolerated; ranking still works).
    ngram_range : (int, int)
        Inclusive range of n-gram sizes. `(1, 1)` = unigrams; `(1, 2)` =
        unigrams + bigrams.
    min_df : int
        Minimum document frequency for a token to enter the vocabulary.
    max_df_ratio : float
        Maximum document-frequency ratio (df/N) for a token to enter the
        vocabulary. Tokens appearing in more than this fraction of the
        corpus are dropped (typically stopwords or universal tokens).
    """

    def __init__(
        self,
        dim: int = 4096,
        ngram_range: tuple[int, int] = (1, 2),
        *,
        min_df: int = 1,
        max_df_ratio: float = 1.0,
    ) -> None:
        if dim <= 0:
            raise RagError("TfidfTextVectorizer requires dim > 0")
        if not (1 <= ngram_range[0] <= ngram_range[1]):
            raise RagError("ngram_range must satisfy 1 <= min <= max")
        if min_df < 1:
            raise RagError("min_df must be >= 1")
        if not (0.0 < max_df_ratio <= 1.0):
            raise RagError("max_df_ratio must be in (0, 1]")
        self._dim = dim
        self._ngram_range = ngram_range
        self._min_df = min_df
        self._max_df_ratio = max_df_ratio
        self._vocab: dict[str, int] = {}
        self._idf: list[float] = []

    @property
    def dim(self) -> int:
        return self._dim

    def _iter_ngrams(self, text: str):
        tokens = _tokenize(text)
        for n in range(self._ngram_range[0], self._ngram_range[1] + 1):
            yield from _ngrams(tokens, n)

    def fit(self, texts: list[str]) -> None:
        """Build vocabulary and IDF weights from `texts`."""
        if not texts:
            raise RagError("fit() requires at least one text")
        df: dict[str, int] = {}
        for text in texts:
            seen: set[str] = set()
            for ng in self._iter_ngrams(text):
                if ng in seen:
                    continue
                seen.add(ng)
                df[ng] = df.get(ng, 0) + 1
        n_docs = len(texts)
        max_df = max(1, int(self._max_df_ratio * n_docs))
        # Apply min_df and max_df_ratio filters.
        kept: dict[str, int] = {
            ng: count for ng, count in df.items() if count >= self._min_df and count <= max_df
        }
        # Assign bucket via hashing trick for stable, fixed-dim layout.
        # Use a sorted set for deterministic vocabulary ordering.
        sorted_tokens = sorted(kept.keys())
        vocab: dict[str, int] = {}
        for token in sorted_tokens:
            h = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(h, "little") % self._dim
            # If a collision happens, we keep the same bucket; this is the
            # standard hashing-trick behaviour. The vector still represents
            # the document, just with a slight collision penalty.
            vocab[token] = bucket
        # Compute IDF per bucket (max over tokens mapped to that bucket).
        idf_per_bucket: dict[int, float] = {}
        for token, bucket in vocab.items():
            idf = math.log((1 + n_docs) / (1 + kept[token])) + 1.0
            if bucket not in idf_per_bucket or idf > idf_per_bucket[bucket]:
                idf_per_bucket[bucket] = idf
        self._vocab = vocab
        self._idf = [idf_per_bucket.get(i, 0.0) for i in range(self._dim)]

    def vectorize(self, texts: list[str]) -> list[list[float]]:
        """Return one TF-IDF weighted, L2-normalized vector per text."""
        if not self._vocab:
            raise RagError("TfidfTextVectorizer has not been fit; call fit(texts) first")
        import numpy as np

        out: list[list[float]] = []
        for text in texts:
            counts: dict[int, float] = {}
            for ng in self._iter_ngrams(text):
                bucket = self._vocab.get(ng)
                if bucket is None:
                    continue
                counts[bucket] = counts.get(bucket, 0.0) + 1.0
            vec = np.zeros(self._dim, dtype=float)
            for bucket, c in counts.items():
                # Sub-linear TF: 1 + log(c).
                vec[bucket] = (1.0 + math.log(c)) * self._idf[bucket]
            n = float(np.linalg.norm(vec))
            if n > 0:
                vec /= n
            out.append([float(x) for x in vec])
        return out

    def save(self, path: Path) -> None:
        """Persist vocabulary and IDF weights as JSON."""
        data = {
            "dim": self._dim,
            "ngram_range": list(self._ngram_range),
            "min_df": self._min_df,
            "max_df_ratio": self._max_df_ratio,
            "vocab": self._vocab,
            "idf": self._idf,
        }
        Path(path).write_text(json.dumps(data))

    @classmethod
    def load(cls, path: Path) -> TfidfTextVectorizer:
        """Restore a previously saved vectorizer."""
        raw = json.loads(Path(path).read_text())
        v = cls(
            dim=raw["dim"],
            ngram_range=tuple(raw["ngram_range"]),
            min_df=raw["min_df"],
            max_df_ratio=raw["max_df_ratio"],
        )
        v._vocab = {k: int(val) for k, val in raw["vocab"].items()}
        v._idf = [float(x) for x in raw["idf"]]
        return v
