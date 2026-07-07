"""Tests for bainary.rag — offline, no embeddings."""

from __future__ import annotations

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
