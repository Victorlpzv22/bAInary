"""bAInary RAG subsystem (C): cross-binary textual-similarity index of functions.

No embedding model — vectorization is local (hashing trick by default).
"""

from bainary.rag.errors import RagError
from bainary.rag.index import Index
from bainary.rag.store import InMemoryStore, NumpyFileStore, SearchHit, VectorRecord, VectorStore
from bainary.rag.text import TEXT_VERSION, build_text
from bainary.rag.vectorize import (
    HashingTextVectorizer,
    TextualVectorizer,
    TfidfTextVectorizer,
    create_textual_vectorizer,
)

__all__ = [
    "RagError",
    "Index",
    "TextualVectorizer",
    "HashingTextVectorizer",
    "TfidfTextVectorizer",
    "create_textual_vectorizer",
    "VectorStore",
    "InMemoryStore",
    "NumpyFileStore",
    "VectorRecord",
    "SearchHit",
    "build_text",
    "TEXT_VERSION",
]
