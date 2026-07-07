"""bAInary RAG subsystem (C): semantic function index and search."""

from bainary.rag.client import (
    EmbeddingClient,
    HashMockEmbeddings,
    OpenAICompatibleEmbeddings,
    create_embedding_client,
)
from bainary.rag.errors import RagError

__all__ = [
    "RagError",
    "EmbeddingClient",
    "HashMockEmbeddings",
    "OpenAICompatibleEmbeddings",
    "create_embedding_client",
]
