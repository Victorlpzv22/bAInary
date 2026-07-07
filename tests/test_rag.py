"""Tests for bainary.rag — unit tests with HashMockEmbeddings + InMemoryStore, no network."""

from __future__ import annotations

import pytest

from bainary.lift.artifact import BinaryArtifact, Function  # noqa: F401
from bainary.lift.errors import BainaryError
from bainary.rag import RagError
from bainary.rag.client import (
    EmbeddingClient,
    HashMockEmbeddings,
    OpenAICompatibleEmbeddings,
    create_embedding_client,
)
from bainary.rag.errors import RagError as RagErrorDirect
from bainary.rag.store import InMemoryStore, NumpyFileStore, SearchHit, VectorRecord
from bainary.rag.text import TEXT_VERSION, build_text
from bainary.rag.index import Index


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


# --- Vector store tests ---


def _make_record(
    id: str = "r1",
    vector: list[float] | None = None,
    binary_sha256: str = "ab" * 32,
    name: str = "main",
    address: str = "0x1000",
    source: str = "/tmp/test.elf",
    text_hash: str = "deadbeef",
) -> VectorRecord:
    fn = Function(
        address=address,
        name=name,
        signature=f"int {name}(void)",
        calling_convention="cdecl",
        size_bytes=16,
        assembly="ret",
        pseudocode="int x() { return 0; }",
    )
    return VectorRecord(
        id=id,
        vector=vector or [1.0, 0.0, 0.0],
        function=fn.to_dict(),
        binary_sha256=binary_sha256,
        name=name,
        address=address,
        source=source,
        text_hash=text_hash,
    )


def test_inmemory_upsert_and_count():
    store = InMemoryStore(dim=3)
    store.upsert([_make_record(id="r1")])
    assert store.count() == 1
    store.upsert([_make_record(id="r2", vector=[0.0, 1.0, 0.0])])
    assert store.count() == 2


def test_inmemory_upsert_same_id_overwrites():
    store = InMemoryStore(dim=3)
    r = _make_record(id="r1", vector=[1.0, 0.0, 0.0])
    store.upsert([r])
    r2 = _make_record(id="r1", vector=[0.0, 0.0, 1.0], text_hash="new")
    store.upsert([r2])
    assert store.count() == 1


def test_inmemory_search_top_k():
    store = InMemoryStore(dim=3)
    store.upsert([_make_record(id="r1", vector=[1.0, 0.0, 0.0])])
    store.upsert([_make_record(id="r2", vector=[0.0, 1.0, 0.0])])
    store.upsert([_make_record(id="r3", vector=[0.0, 0.0, 1.0])])
    hits = store.search([1.0, 0.0, 0.0], k=2)
    assert len(hits) == 2
    assert hits[0].function.name == "main"
    assert hits[0].score > 0.99  # cosine with self ≈ 1


def test_inmemory_search_empty_returns_empty():
    store = InMemoryStore(dim=3)
    assert store.search([1.0, 0.0, 0.0], k=5) == []


def test_inmemory_remove_binary():
    store = InMemoryStore(dim=3)
    store.upsert([_make_record(id="r1", binary_sha256="ab" * 32)])
    store.upsert([_make_record(id="r2", binary_sha256="cd" * 32)])
    removed = store.remove_binary("ab" * 32)
    assert removed == 1
    assert store.count() == 1


def test_inmemory_remove_binary_none():
    store = InMemoryStore(dim=3)
    assert store.remove_binary("ab" * 32) == 0


def test_search_hit_fields():
    hit = SearchHit(
        function=Function(
            address="0x1",
            name="x",
            signature="void x()",
            calling_convention="cdecl",
            size_bytes=1,
            assembly="ret",
        ),
        binary_sha256="ab" * 32,
        score=0.42,
        source="/tmp/test.elf",
    )
    assert hit.function.name == "x"
    assert hit.binary_sha256 == "ab" * 32
    assert hit.score == 0.42
    assert hit.source == "/tmp/test.elf"


def test_numpyfilestore_persistence(tmp_path):
    store = NumpyFileStore(root=tmp_path, dim=3)
    store.upsert([_make_record(id="r1", vector=[1.0, 0.0, 0.0])])
    store.upsert([_make_record(id="r2", vector=[0.0, 1.0, 0.0])])
    store.flush()
    assert store.count() == 2

    store2 = NumpyFileStore(root=tmp_path, dim=3)
    assert store2.count() == 2
    hits = store2.search([1.0, 0.0, 0.0], k=1)
    assert len(hits) == 1
    assert hits[0].function.name == "main"


def test_numpyfilestore_default_root():
    store = NumpyFileStore(dim=3)
    assert store.count() >= 0
    store.flush()
    store.close()


def test_numpyfilestore_corrupt_records_recovers(tmp_path):
    store = NumpyFileStore(root=tmp_path, dim=3)
    store.upsert([_make_record(id="r1")])
    store.flush()
    records_path = tmp_path / "records.json"
    records_path.write_text("{not valid json")
    store2 = NumpyFileStore(root=tmp_path, dim=3)
    assert store2.count() == 0


def test_numpyfilestore_corrupt_npy_recovers(tmp_path):
    store = NumpyFileStore(root=tmp_path, dim=3)
    store.upsert([_make_record(id="r1", vector=[1.0, 0.0, 0.0])])
    store.flush()
    (tmp_path / "store.npy").write_bytes(b"garbage")
    store2 = NumpyFileStore(root=tmp_path, dim=3)
    assert store2.count() == 0


def test_numpyfilestore_remove_binary(tmp_path):
    store = NumpyFileStore(root=tmp_path, dim=3)
    store.upsert([_make_record(id="r1", binary_sha256="ab" * 32)])
    store.upsert([_make_record(id="r2", binary_sha256="cd" * 32)])
    store.flush()
    removed = store.remove_binary("ab" * 32)
    assert removed == 1
    store.flush()
    store2 = NumpyFileStore(root=tmp_path, dim=3)
    assert store2.count() == 1


# --- Index tests ---


def _fn_dict_rag(
    address: str,
    name: str,
    pseudocode: str | None = "// stub",
    assembly: str = "ret",
    size_bytes: int = 16,
) -> dict:
    return {
        "address": address,
        "name": name,
        "signature": f"int {name}(void)",
        "calling_convention": "cdecl",
        "size_bytes": size_bytes,
        "is_thunk": False,
        "basic_blocks": [],
        "cfg": {"nodes": [], "edges": []},
        "callers": [],
        "callees": [],
        "assembly": assembly,
        "pseudocode": pseudocode,
        "pseudocode_error": None,
        "decompiler": "ghidra",
        "stack_frame": {"size": 0, "locals": []},
    }


def _make_artifact_rag(
    functions: list[dict], binary_sha: str = "ab" * 32, path: str = "/tmp/test.elf"
) -> BinaryArtifact:
    return BinaryArtifact.from_dict(
        {
            "schema_version": "1.0",
            "binary": {
                "path": path,
                "sha256": binary_sha,
                "format": "ELF",
                "arch": "x64",
                "endianness": "little",
                "entry_point": "0x401000",
                "base_address": "0x400000",
                "decompiler_version": "test",
            },
            "sections": [],
            "imports": [],
            "exports": [],
            "strings": [],
            "functions": functions,
        }
    )


def _test_artifact_rag() -> BinaryArtifact:
    return _make_artifact_rag(
        [
            _fn_dict_rag("0x1000", "main", pseudocode="int main() { return 0; }"),
            _fn_dict_rag("0x2000", "add", pseudocode="int add() { return 1; }"),
            _fn_dict_rag("0x3000", "no_pseudo", pseudocode=None),
            _fn_dict_rag("0x4000", "empty", pseudocode=None, assembly=""),
        ]
    )


def test_index_add_artifact(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art = _test_artifact_rag()
    idx.add_artifact(art)
    # 3 functions with text (main, add, no_pseudo via ASM); empty has no text
    assert len(idx) == 3


def test_index_search_text_query(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    idx.add_artifact(_test_artifact_rag())
    hits = idx.search("find main", k=2)
    assert len(hits) <= 2
    assert hits[0].score >= hits[-1].score


def test_index_search_similar_returns_self(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art = _test_artifact_rag()
    idx.add_artifact(art)
    fn = art.functions[0]
    hits = idx.search_similar(fn, k=1)
    assert len(hits) == 1
    assert hits[0].function.name == "main"


def test_index_cross_binary_corpus(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art1 = _test_artifact_rag()
    art2 = _make_artifact_rag(
        [_fn_dict_rag("0x5000", "other_main", pseudocode="int other_main() { return 42; }")],
        binary_sha="cd" * 32,
        path="/tmp/other.elf",
    )
    idx.add_artifact(art1)
    idx.add_artifact(art2)
    assert len(idx) == 4
    hits = idx.search("other_main", k=4)
    names = {h.function.name for h in hits}
    assert "other_main" in names


def test_index_re_add_is_noop(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art = _test_artifact_rag()
    idx.add_artifact(art)
    idx.add_artifact(art)
    assert len(idx) == 3


def test_index_text_change_re_embeds(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art1 = _test_artifact_rag()
    idx.add_artifact(art1)
    art2 = _test_artifact_rag()
    art2.functions[0].pseudocode = "int main() { return 99; }"
    idx.add_artifact(art2)
    assert len(idx) == 3


def test_index_skip_no_text(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(
        embeddings=emb,
        store=InMemoryStore(dim=32),
        embedding_cache_root=tmp_path,
        skip_no_text=True,
    )
    art = _make_artifact_rag([_fn_dict_rag("0x1", "empty", pseudocode=None, assembly="")])
    idx.add_artifact(art)
    assert len(idx) == 0


def test_index_no_skip_no_text_raises(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(
        embeddings=emb,
        store=InMemoryStore(dim=32),
        embedding_cache_root=tmp_path,
        skip_no_text=False,
    )
    art = _make_artifact_rag([_fn_dict_rag("0x1", "empty", pseudocode=None, assembly="")])
    with pytest.raises(RagError, match="empty text"):
        idx.add_artifact(art)


def test_index_embedding_cache_hit_skips_client(tmp_path):
    class CountingClient(HashMockEmbeddings):
        def __init__(self) -> None:
            super().__init__(dim=32)
            self.call_count = 0

        def embed(self, texts):
            self.call_count += len(texts)
            return super().embed(texts)

    emb = CountingClient()
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art = _test_artifact_rag()
    idx.add_artifact(art)
    first_calls = emb.call_count
    idx.add_artifact(art)
    assert emb.call_count == first_calls


def test_index_remove_artifact(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art = _test_artifact_rag()
    idx.add_artifact(art)
    removed = idx.remove_artifact(art.binary.sha256)
    assert removed == 3
    assert len(idx) == 0


def test_index_remove_artifact_none(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    assert idx.remove_artifact("ab" * 32) == 0


def test_index_retrieve_context_shape(tmp_path):
    emb = HashMockEmbeddings(dim=32)
    from bainary.rag.store import InMemoryStore

    idx = Index(embeddings=emb, store=InMemoryStore(dim=32), embedding_cache_root=tmp_path)
    art = _test_artifact_rag()
    idx.add_artifact(art)
    ctx = idx.retrieve_context(art.functions[0], k=2)
    assert "neighbors" in ctx
    assert isinstance(ctx["neighbors"], list)
    assert len(ctx["neighbors"]) <= 2
    for item in ctx["neighbors"]:
        assert isinstance(item, tuple)
        assert len(item) == 2


def test_index_default_store_is_numpyfilestore(tmp_path):
    idx = Index(
        embeddings=HashMockEmbeddings(dim=8),
        store=NumpyFileStore(root=tmp_path / "rag", dim=8),
        embedding_cache_root=tmp_path / "embcache",
    )
    idx.add_artifact(_test_artifact_rag())
    idx.flush()
    assert (tmp_path / "rag" / "store.npy").exists()
    assert (tmp_path / "rag" / "records.json").exists()


def test_index_embedding_failure_partial(tmp_path):
    class FlakyClient(HashMockEmbeddings):
        def __init__(self, fail_on_text_contains: str) -> None:
            super().__init__(dim=32)
            self._fail_on = fail_on_text_contains

        def embed(self, texts):
            if any(self._fail_on in t for t in texts):
                raise RagError("simulated API failure")
            return super().embed(texts)

    from bainary.rag.store import InMemoryStore

    idx = Index(
        embeddings=FlakyClient(fail_on_text_contains="add"),
        store=InMemoryStore(dim=32),
        embedding_cache_root=tmp_path,
    )
    idx.add_artifact(_test_artifact_rag())
    # main + no_pseudo indexed; add skipped
    assert len(idx) == 2


def test_index_len_and_search_empty(tmp_path):
    from bainary.rag.store import InMemoryStore

    idx = Index(
        embeddings=HashMockEmbeddings(dim=32),
        store=InMemoryStore(dim=32),
        embedding_cache_root=tmp_path,
    )
    assert len(idx) == 0
    assert idx.search("anything", k=5) == []
