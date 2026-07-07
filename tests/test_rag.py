"""Tests for bainary.rag — unit tests with HashMockEmbeddings + InMemoryStore, no network."""

from __future__ import annotations

import pytest

from bainary.lift.artifact import Function
from bainary.lift.errors import BainaryError
from bainary.rag import RagError
from bainary.rag.client import (
    EmbeddingClient,
    HashMockEmbeddings,
    OpenAICompatibleEmbeddings,
    create_embedding_client,
)
from bainary.rag.errors import RagError as RagErrorDirect
from bainary.rag.text import TEXT_VERSION, build_text


def test_rag_error_is_bainary_error():
    assert issubclass(RagError, BainaryError)
    assert RagError is RagErrorDirect


def test_text_version_is_string():
    assert isinstance(TEXT_VERSION, str)
    assert TEXT_VERSION


def test_build_text_includes_name_and_signature():
    fn = Function(
        address="0x1000",
        name="main",
        signature="int main(int argc, char ** argv)",
        calling_convention="cdecl",
        size_bytes=64,
        assembly="ret",
        pseudocode="int main() { return 0; }",
    )
    text = build_text(fn)
    assert "main" in text
    assert "int main(int argc, char ** argv)" in text
    assert "int main() { return 0; }" in text


def test_build_text_falls_back_to_assembly_when_no_pseudocode():
    fn = Function(
        address="0x2000",
        name="add",
        signature="int add(void)",
        calling_convention="cdecl",
        size_bytes=8,
        assembly="mov eax, 1\nret",
        pseudocode=None,
    )
    text = build_text(fn)
    assert "mov eax, 1" in text
    assert "no decompilation available" in text.lower()


def test_build_text_empty_when_no_pseudocode_and_no_assembly():
    fn = Function(
        address="0x3000",
        name="stub",
        signature="void stub(void)",
        calling_convention="cdecl",
        size_bytes=0,
        assembly="",
        pseudocode=None,
    )
    assert build_text(fn) == ""


def test_hash_mock_embeddings_is_embedding_client():
    emb = HashMockEmbeddings(dim=64)
    assert isinstance(emb, EmbeddingClient)


def test_hash_mock_embeddings_dim():
    emb = HashMockEmbeddings(dim=32)
    assert emb.dim == 32
    assert emb.model_name == "mock"


def test_hash_mock_embeddings_deterministic():
    emb = HashMockEmbeddings(dim=64)
    v1 = emb.embed(["hello world"])[0]
    v2 = emb.embed(["hello world"])[0]
    assert len(v1) == 64
    assert v1 == v2


def test_hash_mock_embeddings_different_text_different_vector():
    emb = HashMockEmbeddings(dim=64)
    v1 = emb.embed(["foo"])[0]
    v2 = emb.embed(["bar baz quux totally different"])[0]
    assert v1 != v2


def test_hash_mock_embeddings_batch():
    emb = HashMockEmbeddings(dim=8)
    out = emb.embed(["one", "two", "three"])
    assert len(out) == 3
    assert all(len(v) == 8 for v in out)


def test_create_client_mock():
    emb = create_embedding_client(provider="mock", dim=16)
    assert isinstance(emb, HashMockEmbeddings)
    assert emb.dim == 16


def test_create_client_openai_no_api_key_raises():
    with pytest.raises(RagError, match="api_key"):
        create_embedding_client(provider="openai")


def test_create_client_openai():
    emb = create_embedding_client(
        provider="openai",
        api_key="sk-test",
        base_url="https://example.com/v1",
        model="text-embedding-3-small",
    )
    assert isinstance(emb, OpenAICompatibleEmbeddings)
    assert emb.model_name == "text-embedding-3-small"


def test_create_client_unknown_provider():
    with pytest.raises(RagError, match="unknown provider"):
        create_embedding_client(provider="cohere")
