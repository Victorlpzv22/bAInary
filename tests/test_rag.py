"""Tests for bainary.rag — offline, no embeddings."""

from __future__ import annotations

from pathlib import Path

import pytest

from bainary.lift.artifact import BinaryArtifact, Function
from bainary.lift.errors import BainaryError
from bainary.rag import (
    HashingTextVectorizer,
    Index,
    InMemoryStore,
    NumpyFileStore,
    RagError,
    SearchHit,
    TextualVectorizer,
    VectorRecord,
    build_text,
)
from bainary.rag.errors import RagError as RagErrorDirect
from bainary.rag.text import TEXT_VERSION
from bainary.rag.vectorize import create_textual_vectorizer


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


# --- TextualVectorizer tests ---


def test_hashing_text_vectorizer_is_textual_vectorizer():
    v = HashingTextVectorizer(dim=64)
    assert isinstance(v, TextualVectorizer)


def test_hashing_text_vectorizer_dim():
    v = HashingTextVectorizer(dim=32)
    assert v.dim == 32


def test_hashing_text_vectorizer_deterministic():
    v = HashingTextVectorizer(dim=64)
    v1 = v.vectorize(["hello world"])[0]
    v2 = v.vectorize(["hello world"])[0]
    assert len(v1) == 64
    assert v1 == v2


def test_hashing_text_vectorizer_different_text_different_vector():
    v = HashingTextVectorizer(dim=64)
    v1 = v.vectorize(["foo bar baz"])[0]
    v2 = v.vectorize(["completely different tokens xyzzy plover"])[0]
    assert v1 != v2


def test_hashing_text_vectorizer_batch():
    v = HashingTextVectorizer(dim=8)
    out = v.vectorize(["one", "two", "three"])
    assert len(out) == 3
    assert all(len(vec) == 8 for vec in out)


def test_hashing_text_vectorizer_similar_text_higher_score():
    """Two texts sharing many n-grams should be more similar than two disjoint ones."""
    import numpy as np

    v = HashingTextVectorizer(dim=256)
    a = v.vectorize(["int main() { printf hello; return 0; }"])[0]
    b = v.vectorize(["int main() { printf world; return 1; }"])[0]
    c = v.vectorize(["totally unrelated banana kite fishing"])[0]

    def cos(x, y):
        xn, yn = np.array(x), np.array(y)
        nx, ny = np.linalg.norm(xn), np.linalg.norm(yn)
        if nx == 0 or ny == 0:
            return 0.0
        return float(np.dot(xn, yn) / (nx * ny))

    assert cos(a, b) > cos(a, c)


def test_hashing_text_vectorizer_empty_text():
    v = HashingTextVectorizer(dim=32)
    out = v.vectorize([""])[0]
    assert len(out) == 32
    assert all(x == 0.0 for x in out)


def test_create_textual_vectorizer_default():
    v = create_textual_vectorizer()
    assert isinstance(v, HashingTextVectorizer)
    assert v.dim == 1024


def test_hashing_text_vectorizer_invalid_dim():
    with pytest.raises(RagError, match="dim > 0"):
        HashingTextVectorizer(dim=0)


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
    assert hits[0].score > 0.99


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
            _fn_dict_rag(
                "0x1000",
                "main",
                pseudocode="int main() { return 0; }",
            ),
            _fn_dict_rag("0x2000", "add", pseudocode="int add() { return 1; }"),
            _fn_dict_rag("0x3000", "no_pseudo", pseudocode=None),
            _fn_dict_rag("0x4000", "empty", pseudocode=None, assembly=""),
        ]
    )


def test_index_add_artifact():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
    art = _test_artifact_rag()
    idx.add_artifact(art)
    # 3 functions with text (main, add, no_pseudo via ASM); empty has no text
    assert len(idx) == 3


def test_index_search_text_query():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
    idx.add_artifact(_test_artifact_rag())
    hits = idx.search("find main", k=2)
    assert len(hits) <= 2
    assert hits[0].score >= hits[-1].score


def test_index_search_similar_returns_self():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
    art = _test_artifact_rag()
    idx.add_artifact(art)
    fn = art.functions[0]
    hits = idx.search_similar(fn, k=1)
    assert len(hits) == 1
    assert hits[0].function.name == "main"
    assert hits[0].score > 0.99


def test_index_cross_binary_corpus():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
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


def test_index_re_add_is_noop():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
    art = _test_artifact_rag()
    idx.add_artifact(art)
    idx.add_artifact(art)
    assert len(idx) == 3


def test_index_skip_no_text():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(
        vectorizer=vec,
        store=InMemoryStore(dim=128),
        skip_no_text=True,
    )
    art = _make_artifact_rag([_fn_dict_rag("0x1", "empty", pseudocode=None, assembly="")])
    idx.add_artifact(art)
    assert len(idx) == 0


def test_index_no_skip_no_text_raises():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(
        vectorizer=vec,
        store=InMemoryStore(dim=128),
        skip_no_text=False,
    )
    art = _make_artifact_rag([_fn_dict_rag("0x1", "empty", pseudocode=None, assembly="")])
    with pytest.raises(RagError, match="empty text"):
        idx.add_artifact(art)


def test_index_remove_artifact():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
    art = _test_artifact_rag()
    idx.add_artifact(art)
    removed = idx.remove_artifact(art.binary.sha256)
    assert removed == 3
    assert len(idx) == 0


def test_index_remove_artifact_none():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
    assert idx.remove_artifact("ab" * 32) == 0


def test_index_retrieve_context_shape():
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
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
        vectorizer=HashingTextVectorizer(dim=8),
        store=NumpyFileStore(root=tmp_path / "rag", dim=8),
    )
    idx.add_artifact(_test_artifact_rag())
    idx.flush()
    assert (tmp_path / "rag" / "store.npy").exists()
    assert (tmp_path / "rag" / "records.json").exists()


def test_index_vectorize_failure_partial():
    class FlakyVectorizer(TextualVectorizer):
        def __init__(self, fail_on_text_contains: str) -> None:
            self._dim = 32
            self._fail_on = fail_on_text_contains

        @property
        def dim(self) -> int:
            return self._dim

        def vectorize(self, texts):
            if any(self._fail_on in t for t in texts):
                raise RagError("simulated vectorize failure")
            return HashingTextVectorizer(dim=self._dim).vectorize(texts)

    idx = Index(
        vectorizer=FlakyVectorizer(fail_on_text_contains="add"),
        store=InMemoryStore(dim=32),
    )
    idx.add_artifact(_test_artifact_rag())
    # main + no_pseudo indexed; add skipped
    assert len(idx) == 2


def test_index_len_and_search_empty():
    vec = HashingTextVectorizer(dim=32)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=32))
    assert len(idx) == 0
    assert idx.search("anything", k=5) == []


def test_index_search_finds_similar_across_binaries():
    """Two functions with similar pseudocode should rank closer than unrelated ones."""
    vec = HashingTextVectorizer(dim=256)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=256))
    art1 = _make_artifact_rag(
        [
            _fn_dict_rag(
                "0x1000",
                "parse_http_header",
                pseudocode=(
                    "int parse_http_header(char * buf, int len) "
                    "{ if (buf[0] == 'G') return 200; return 404; }"
                ),
            )
        ],
        binary_sha="aa" * 32,
    )
    art2 = _make_artifact_rag(
        [
            _fn_dict_rag(
                "0x2000",
                "parse_https_header",
                pseudocode=(
                    "int parse_https_header(char * buf, int len) "
                    "{ if (buf[0] == 'G') return 200; return 404; }"
                ),
            ),
            _fn_dict_rag(
                "0x3000",
                "cook_egg",
                pseudocode="int cook_egg() { return 1; }",
            ),
        ],
        binary_sha="bb" * 32,
    )
    idx.add_artifact(art1)
    idx.add_artifact(art2)
    fn = art1.functions[0]
    hits = idx.search_similar(fn, k=2)
    assert hits[0].function.name == "parse_http_header"
    assert hits[1].function.name == "parse_https_header"


# --- VectorStore: list_by_binary / remove_by_id tests ---


def test_inmemory_list_by_binary():
    store = InMemoryStore(dim=3)
    store.upsert([_make_record(id="r1", binary_sha256="ab" * 32)])
    store.upsert([_make_record(id="r2", binary_sha256="ab" * 32, address="0x2000")])
    store.upsert([_make_record(id="r3", binary_sha256="cd" * 32, address="0x3000")])
    out = store.list_by_binary("ab" * 32)
    assert {r.id for r in out} == {"r1", "r2"}


def test_inmemory_list_by_binary_empty():
    store = InMemoryStore(dim=3)
    assert store.list_by_binary("ab" * 32) == []


def test_inmemory_remove_by_id():
    store = InMemoryStore(dim=3)
    store.upsert([_make_record(id="r1")])
    store.upsert([_make_record(id="r2", vector=[0.0, 1.0, 0.0])])
    assert store.remove_by_id("r1") is True
    assert store.count() == 1
    assert store.remove_by_id("r1") is False
    assert store.remove_by_id("missing") is False


def test_numpyfilestore_list_by_binary(tmp_path):
    store = NumpyFileStore(root=tmp_path, dim=3)
    store.upsert([_make_record(id="r1", binary_sha256="ab" * 32)])
    store.upsert([_make_record(id="r2", binary_sha256="ab" * 32, address="0x2000")])
    store.upsert([_make_record(id="r3", binary_sha256="cd" * 32, address="0x3000")])
    store.flush()
    out = store.list_by_binary("ab" * 32)
    assert {r.id for r in out} == {"r1", "r2"}


def test_numpyfilestore_remove_by_id(tmp_path):
    store = NumpyFileStore(root=tmp_path, dim=3)
    store.upsert([_make_record(id="r1")])
    store.upsert([_make_record(id="r2", vector=[0.0, 1.0, 0.0])])
    store.flush()
    assert store.remove_by_id("r1") is True
    store.flush()
    store2 = NumpyFileStore(root=tmp_path, dim=3)
    assert store2.count() == 1
    assert store2.remove_by_id("missing") is False


# --- Index: gc_orphans tests ---


def test_gc_orphans_no_orphans():
    vec = HashingTextVectorizer(dim=64)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=64))
    art = _test_artifact_rag()
    idx.add_artifact(art)
    assert idx.gc_orphans(art) == 0
    assert len(idx) == 3


def test_gc_orphans_removes_stale_addresses():
    """Re-lift with shifted addresses: orphans from the old layout get removed."""
    vec = HashingTextVectorizer(dim=64)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=64))
    art_v1 = _make_artifact_rag(
        [
            _fn_dict_rag("0x1000", "a", pseudocode="int a() { return 0; }"),
            _fn_dict_rag("0x2000", "b", pseudocode="int b() { return 1; }"),
        ],
        binary_sha="ee" * 32,
    )
    idx.add_artifact(art_v1)
    assert len(idx) == 2

    art_v2 = _make_artifact_rag(
        [
            _fn_dict_rag("0x5000", "a", pseudocode="int a() { return 0; }"),  # shifted
            _fn_dict_rag("0x6000", "b", pseudocode="int b() { return 1; }"),  # shifted
        ],
        binary_sha="ee" * 32,  # same binary
    )
    # add_artifact inserts the new ones but leaves the old ids as orphans.
    idx.add_artifact(art_v2)
    assert len(idx) == 4  # 2 stale + 2 fresh

    removed = idx.gc_orphans(art_v2)
    assert removed == 2
    assert len(idx) == 2
    # Survivors are the fresh ones.
    names = {
        f.name
        for f in [Function.from_dict(r.function) for r in idx._store.list_by_binary("ee" * 32)]
    }
    assert names == {"a", "b"}


def test_gc_orphans_idempotent():
    vec = HashingTextVectorizer(dim=64)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=64))
    art_v1 = _make_artifact_rag(
        [
            _fn_dict_rag("0x1000", "a", pseudocode="int a() { return 0; }"),
            _fn_dict_rag("0x2000", "b", pseudocode="int b() { return 1; }"),
        ],
        binary_sha="ee" * 32,
    )
    art_v2 = _make_artifact_rag(
        [
            _fn_dict_rag("0x5000", "a", pseudocode="int a() { return 0; }"),
            _fn_dict_rag("0x6000", "b", pseudocode="int b() { return 1; }"),
        ],
        binary_sha="ee" * 32,
    )
    idx.add_artifact(art_v1)
    idx.add_artifact(art_v2)
    assert idx.gc_orphans(art_v2) == 2
    assert idx.gc_orphans(art_v2) == 0


def test_gc_orphans_does_not_touch_other_binaries():
    vec = HashingTextVectorizer(dim=64)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=64))
    art_a = _make_artifact_rag(
        [_fn_dict_rag("0x1", "aa", pseudocode="int aa() { return 0; }")],
        binary_sha="aa" * 32,
    )
    art_b_v1 = _make_artifact_rag(
        [_fn_dict_rag("0x10", "bb", pseudocode="int bb() { return 0; }")],
        binary_sha="bb" * 32,
    )
    art_b_v2 = _make_artifact_rag(
        [_fn_dict_rag("0x20", "bb", pseudocode="int bb() { return 0; }")],
        binary_sha="bb" * 32,
    )
    idx.add_artifact(art_a)
    idx.add_artifact(art_b_v1)
    idx.add_artifact(art_b_v2)
    assert len(idx) == 3
    assert idx.gc_orphans(art_b_v2) == 1
    assert len(idx) == 2
    # art_a untouched.
    assert idx._store.get(_record_id_test("aa" * 32, "0x1")) is not None


def test_gc_orphans_no_binary_in_corpus():
    vec = HashingTextVectorizer(dim=64)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=64))
    art = _make_artifact_rag(
        [_fn_dict_rag("0x1", "x", pseudocode="int x() { return 0; }")],
        binary_sha="ff" * 32,
    )
    # Corpus is empty; gc_orphans should be a no-op returning 0.
    assert idx.gc_orphans(art) == 0


def _record_id_test(binary_sha: str, fn_address: str) -> str:
    import hashlib

    return hashlib.sha256(f"{binary_sha}:{fn_address}".encode()).hexdigest()


# --- TfidfTextVectorizer tests ---


def test_tfidf_vectorize_before_fit_raises():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=16)
    with pytest.raises(RagError, match="fit"):
        v.vectorize(["hello"])


def test_tfidf_fit_then_vectorize_dim():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=64)
    v.fit(["foo bar baz", "qux quux"])
    out = v.vectorize(["foo bar"])[0]
    assert len(out) == 64
    assert v.dim == 64


def test_tfidf_deterministic_after_fit():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=32)
    v.fit(["alpha beta gamma", "delta epsilon zeta", "eta theta iota"])
    a = v.vectorize(["alpha beta"])[0]
    b = v.vectorize(["alpha beta"])[0]
    assert a == b


def test_tfidf_different_text_different_vector():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=32)
    v.fit(["alpha beta", "gamma delta", "epsilon zeta"])
    a = v.vectorize(["alpha beta"])[0]
    b = v.vectorize(["completely unrelated nonsense xyzzy"])[0]
    assert a != b


def test_tfidf_idf_weights_rare_token_higher():
    from bainary.rag.vectorize import TfidfTextVectorizer

    corpus = [
        "common common common common",
        "common rare_word",
        "common another",
    ]
    v = TfidfTextVectorizer(dim=64, ngram_range=(1, 1))
    v.fit(corpus)
    assert "common" in v._vocab
    assert "rare_word" in v._vocab
    idf_common = v._idf[v._vocab["common"]]
    idf_rare = v._idf[v._vocab["rare_word"]]
    assert idf_rare > idf_common


def test_tfidf_save_load_roundtrip(tmp_path):
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=32, ngram_range=(1, 1))
    v.fit(["foo bar", "baz qux", "alpha beta"])
    path = tmp_path / "tfidf.json"
    v.save(path)

    v2 = TfidfTextVectorizer.load(path)
    assert v2.dim == v.dim
    a = v.vectorize(["foo"])[0]
    b = v2.vectorize(["foo"])[0]
    assert a == b


def test_tfidf_ngram_range_1_2():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=128, ngram_range=(1, 2))
    v.fit(["int main()", "void foo()", "char * bar()"])
    v.vectorize(["int main()"])
    assert v._vocab.get("int") is not None
    assert v._vocab.get("main") is not None
    assert v._vocab.get("int main") is not None


def test_tfidf_min_df_filters_rare_tokens():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=64, ngram_range=(1, 1), min_df=2)
    v.fit(["foo bar", "foo baz", "alpha beta"])
    assert "alpha" not in v._vocab
    assert "beta" not in v._vocab
    assert "foo" in v._vocab


def test_tfidf_max_df_ratio_filters_common_tokens():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=64, ngram_range=(1, 1), max_df_ratio=0.5)
    v.fit(
        [
            "common a",
            "common b",
            "common c",
            "common d",
            "rare x",
        ]
    )
    assert "common" not in v._vocab
    assert "rare" in v._vocab


def test_tfidf_is_textual_vectorizer():
    from bainary.rag.vectorize import TfidfTextVectorizer

    v = TfidfTextVectorizer(dim=8)
    v.fit(["hello world", "foo bar"])
    assert isinstance(v, TextualVectorizer)


# --- CLI tests ---


def test_cli_index_search_roundtrip(tmp_path):
    """End-to-end: lift hello.elf, index, search 'main', find it."""
    from typer.testing import CliRunner

    from bainary.rag.cli import app

    fixture = Path(__file__).resolve().parent / "fixtures" / "hello_elf64" / "hello.elf"
    assert fixture.exists(), f"fixture missing: {fixture}"

    store_root = tmp_path / "store"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["index", str(fixture), "--store-root", str(store_root)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr

    result = runner.invoke(
        app,
        ["search", "main", "--store-root", str(store_root), "-k", "5"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    # The output should contain at least one line with 'main'.
    assert "main" in result.stdout.lower()


def test_cli_search_empty_corpus(tmp_path):
    from typer.testing import CliRunner

    from bainary.rag.cli import app

    store_root = tmp_path / "store"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["search", "anything", "--store-root", str(store_root), "-k", "5"],
    )
    assert result.exit_code == 0
    # Empty corpus: 0 hits header line, no rows.
    assert "0 hits" in result.stdout or "count: 0" in result.stdout.lower()


def test_cli_search_k_flag(tmp_path):
    from typer.testing import CliRunner

    from bainary.rag.cli import app

    fixture = Path(__file__).resolve().parent / "fixtures" / "hello_elf64" / "hello.elf"
    store_root = tmp_path / "store"
    runner = CliRunner()
    runner.invoke(app, ["index", str(fixture), "--store-root", str(store_root)])
    result = runner.invoke(
        app,
        ["search", "function", "--store-root", str(store_root), "-k", "1"],
    )
    assert result.exit_code == 0
    # The data rows are TSV lines starting with the score. We expect exactly
    # one such line (k=1).
    data_lines = [
        line for line in result.stdout.splitlines() if line and line[0].isdigit() and "\t" in line
    ]
    assert len(data_lines) == 1


def test_cli_stats(tmp_path):
    from typer.testing import CliRunner

    from bainary.rag.cli import app

    fixture = Path(__file__).resolve().parent / "fixtures" / "hello_elf64" / "hello.elf"
    store_root = tmp_path / "store"
    runner = CliRunner()
    runner.invoke(app, ["index", str(fixture), "--store-root", str(store_root)])
    result = runner.invoke(app, ["stats", "--store-root", str(store_root)])
    assert result.exit_code == 0
    assert "functions:" in result.stdout
    # After indexing hello.elf we should have more than 0 functions.
    assert "functions: 0" not in result.stdout


def test_cli_stats_empty(tmp_path):
    from typer.testing import CliRunner

    from bainary.rag.cli import app

    store_root = tmp_path / "store"
    runner = CliRunner()
    result = runner.invoke(app, ["stats", "--store-root", str(store_root)])
    assert result.exit_code == 0
    assert "functions: 0" in result.stdout


def test_cli_index_from_artifact(tmp_path):
    """--from-artifact accepts an already-lifted JSON path."""
    from typer.testing import CliRunner

    from bainary.rag.cli import app

    fixture = Path(__file__).resolve().parent / "fixtures" / "hello_elf64" / "hello.elf"
    # Lift to a JSON file first.
    from bainary.lift import lift

    artifact = lift(str(fixture), backend="lief_capstone")
    artifact_path = tmp_path / "artifact.json"
    artifact.to_json(artifact_path)

    store_root = tmp_path / "store"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["index", "--from-artifact", str(artifact_path), "--store-root", str(store_root)],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    # Confirm by stats.
    result = runner.invoke(app, ["stats", "--store-root", str(store_root)])
    assert "functions: 0" not in result.stdout


# --- Metadata filtering tests ---


def _make_index_two_binaries() -> tuple[Index, BinaryArtifact, BinaryArtifact]:
    vec = HashingTextVectorizer(dim=128)
    idx = Index(vectorizer=vec, store=InMemoryStore(dim=128))
    art_a = _make_artifact_rag(
        [
            _fn_dict_rag("0x1000", "parse_http", pseudocode="int parse_http() { return 0; }"),
            _fn_dict_rag("0x2000", "cook_egg", pseudocode="int cook_egg() { return 0; }"),
        ],
        binary_sha="aa" * 32,
    )
    art_b = _make_artifact_rag(
        [
            _fn_dict_rag("0x3000", "parse_https", pseudocode="int parse_https() { return 1; }"),
            _fn_dict_rag("0x4000", "fry_egg", pseudocode="int fry_egg() { return 1; }"),
        ],
        binary_sha="bb" * 32,
    )
    idx.add_artifact(art_a)
    idx.add_artifact(art_b)
    return idx, art_a, art_b


def test_search_filter_by_binary():
    idx, _, art_b = _make_index_two_binaries()
    hits = idx.search("function", k=10, binary_sha=art_b.binary.sha256)
    assert len(hits) > 0
    for h in hits:
        assert h.binary_sha256 == art_b.binary.sha256


def test_search_filter_by_name_regex():
    idx, _, _ = _make_index_two_binaries()
    hits = idx.search("function", k=10, name_regex=r"^parse_")
    names = {h.function.name for h in hits}
    assert names <= {"parse_http", "parse_https"}
    assert "cook_egg" not in names
    assert "fry_egg" not in names


def test_search_filter_by_address_range():
    idx, _, _ = _make_index_two_binaries()
    hits = idx.search("function", k=10, address_range=("0x1000", "0x2fff"))
    addrs = {h.function.address for h in hits}
    assert addrs <= {"0x1000", "0x2000"}
    assert "0x3000" not in addrs
    assert "0x4000" not in addrs


def test_search_filter_combined():
    idx, art_a, _ = _make_index_two_binaries()
    hits = idx.search(
        "function",
        k=10,
        binary_sha=art_a.binary.sha256,
        name_regex=r"^parse_",
    )
    assert len(hits) == 1
    assert hits[0].function.name == "parse_http"


def test_search_filter_no_match():
    idx, _, _ = _make_index_two_binaries()
    hits = idx.search("function", k=10, name_regex=r"^this_does_not_match_anything$")
    assert hits == []


def test_search_no_filter_backwards_compat():
    """Calling search() without any filter kwargs still works."""
    idx, _, _ = _make_index_two_binaries()
    hits = idx.search("function", k=2)
    assert len(hits) == 2
    assert hits[0].score >= hits[-1].score


def test_search_similar_with_filter():
    idx, art_a, _ = _make_index_two_binaries()
    fn = art_a.functions[0]  # parse_http
    hits = idx.search_similar(fn, k=10, binary_sha=art_a.binary.sha256)
    for h in hits:
        assert h.binary_sha256 == art_a.binary.sha256


def test_inmemory_search_with_filters():
    """The InMemoryStore itself honors the filter kwargs."""
    store = InMemoryStore(dim=3)
    store.upsert(
        [
            _make_record(
                id="r1",
                vector=[1.0, 0.0, 0.0],
                binary_sha256="aa" * 32,
                name="foo",
                address="0x1000",
            ),
            _make_record(
                id="r2",
                vector=[0.0, 1.0, 0.0],
                binary_sha256="bb" * 32,
                name="bar",
                address="0x2000",
            ),
            _make_record(
                id="r3",
                vector=[0.0, 0.0, 1.0],
                binary_sha256="aa" * 32,
                name="baz",
                address="0x3000",
            ),
        ]
    )
    hits = store.search([1.0, 0.0, 0.0], k=10, binary_sha="aa" * 32)
    assert {h.function.name for h in hits} == {"foo", "baz"}
    hits = store.search([1.0, 0.0, 0.0], k=10, name_regex=r"^baz$")
    assert {h.function.name for h in hits} == {"baz"}
    hits = store.search([1.0, 0.0, 0.0], k=10, address_range=("0x1500", "0x2fff"))
    assert {h.function.name for h in hits} == {"bar"}


def test_numpyfilestore_search_with_filters(tmp_path):
    store = NumpyFileStore(root=tmp_path, dim=3)
    store.upsert(
        [
            _make_record(
                id="r1",
                vector=[1.0, 0.0, 0.0],
                binary_sha256="aa" * 32,
                name="foo",
                address="0x1000",
            ),
            _make_record(
                id="r2",
                vector=[0.0, 1.0, 0.0],
                binary_sha256="bb" * 32,
                name="bar",
                address="0x2000",
            ),
        ]
    )
    store.flush()
    hits = store.search([1.0, 0.0, 0.0], k=10, binary_sha="aa" * 32)
    assert {h.function.name for h in hits} == {"foo"}
    hits = store.search([1.0, 0.0, 0.0], k=10, name_regex=r"^ba")
    assert {h.function.name for h in hits} == {"bar"}
    hits = store.search([1.0, 0.0, 0.0], k=10, address_range=("0x1500", "0x2fff"))
    assert {h.function.name for h in hits} == {"bar"}
