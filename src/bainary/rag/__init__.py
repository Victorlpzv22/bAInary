"""bAInary RAG subsystem (C): semantic function index and search."""

from bainary.rag.client import (
    EmbeddingClient,
    HashMockEmbeddings,
    OpenAICompatibleEmbeddings,
    create_embedding_client,
)
from bainary.rag.errors import RagError
from bainary.rag.index import Index
from bainary.rag.store import InMemoryStore, NumpyFileStore, SearchHit, VectorRecord, VectorStore

__all__ = [
    "RagError",
    "EmbeddingClient",
    "HashMockEmbeddings",
    "OpenAICompatibleEmbeddings",
    "create_embedding_client",
    "Index",
    "VectorStore",
    "InMemoryStore",
    "NumpyFileStore",
    "VectorRecord",
    "SearchHit",
]
