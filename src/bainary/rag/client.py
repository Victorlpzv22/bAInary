# mypy: ignore-errors
"""Embedding client abstraction with multiple provider support."""

from __future__ import annotations

import hashlib
import struct
from abc import ABC, abstractmethod
from typing import Any

from bainary.rag.errors import RagError


class EmbeddingClient(ABC):
    """Abstract interface for embedding models."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier (e.g. 'text-embedding-3-small')."""

    @property
    @abstractmethod
    def dim(self) -> int:
        """The dimensionality of vectors produced by this model."""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, returning one vector per text.

        Raises
        ------
        RagError
            If the API call fails or returns a vector of unexpected dim.
        """


class HashMockEmbeddings(EmbeddingClient):
    """Deterministic offline embeddings via SHA-256 bucketing.

    Each text is hashed to ``dim`` buckets; the bucket index maps to
    a float in [0, 1) via division. Same text always yields the same
    vector; different texts yield different vectors with high probability.
    """

    def __init__(self, dim: int = 64) -> None:
        if dim <= 0:
            raise RagError("HashMockEmbeddings requires dim > 0")
        self._dim = dim

    @property
    def model_name(self) -> str:
        return "mock"

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            bytes_needed = self._dim * 4
            buf = b""
            counter = 0
            while len(buf) < bytes_needed:
                buf += hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
                counter += 1
            vec = [struct.unpack("<I", buf[i * 4 : i * 4 + 4])[0] / 2**32 for i in range(self._dim)]
            out.append(vec)
        return out


class OpenAICompatibleEmbeddings(EmbeddingClient):
    """Client for OpenAI-compatible embeddings APIs (OpenAI, OpenCode Go, Ollama)."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "text-embedding-3-small",
        *,
        dim: int = 1536,
    ) -> None:
        from openai import OpenAI

        if not api_key:
            raise RagError("api_key required for OpenAICompatibleEmbeddings")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model
        self._dim = dim

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(model=self._model, input=texts)
        except Exception as e:
            raise RagError(f"OpenAI-compatible embeddings call failed: {e}") from e
        out: list[list[float]] = []
        for item in response.data:
            vec = item.embedding
            if len(vec) != self._dim:
                raise RagError(f"embedding dim mismatch: expected {self._dim}, got {len(vec)}")
            out.append([float(x) for x in vec])
        return out


def create_embedding_client(
    provider: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    dim: int | None = None,
) -> EmbeddingClient:
    """Factory for creating an embedding client by provider name."""
    if provider == "mock":
        return HashMockEmbeddings(dim=dim or 64)
    if provider == "openai":
        if not api_key:
            raise RagError("api_key required for provider='openai'")
        return OpenAICompatibleEmbeddings(
            api_key=api_key,
            base_url=base_url,
            model=model or "text-embedding-3-small",
            dim=dim or 1536,
        )
    raise RagError(f"unknown provider {provider!r}; known: openai, mock")
