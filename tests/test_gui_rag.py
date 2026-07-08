"""Tests for bainary.gui.routes.rag — build index, search, similar.

RAG uses a local :class:`HashingTextVectorizer` — no API key required.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app
from bainary.lift.artifact import (
    BinaryArtifact,
    BinaryInfo,
    Cfg,
    ExportRef,
    Function,
    ImportRef,
    Section,
    StringRef,
)

FIXTURE = Path("tests/fixtures/loops_elf64/loops.elf")


def _artifact() -> BinaryArtifact:
    return BinaryArtifact(
        binary=BinaryInfo(
            path=str(FIXTURE),
            sha256="0" * 64,
            format="ELF",
            arch="x64",
            endianness="little",
            entry_point="0x1000",
            base_address="0x0",
        ),
        sections=[Section(name=".text", address="0x1000", size=0x1000, permissions="r-x")],
        imports=[ImportRef(address="0x2000", name="printf", library="libc")],
        exports=[ExportRef(address="0x1000", name="main")],
        strings=[StringRef(address="0x3000", value="hi", encoding="ascii")],
        functions=[
            Function(
                address="0x1000",
                name="main",
                signature="int main(void)",
                calling_convention="cdecl",
                size_bytes=64,
                assembly="",
                is_thunk=False,
                basic_blocks=[],
                cfg=Cfg(),
                callers=[],
                callees=[],
                pseudocode="int main(void) { return 0; }",
            ),
            Function(
                address="0x1100",
                name="helper",
                signature="void helper(void)",
                calling_convention="cdecl",
                size_bytes=16,
                assembly="",
                is_thunk=False,
                basic_blocks=[],
                cfg=Cfg(),
                callers=[],
                callees=[],
                pseudocode="void helper(void) {}",
            ),
        ],
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_build_409_no_artifact(client: TestClient) -> None:
    r = client.post("/api/rag/build")
    assert r.status_code == 409


def test_build_creates_index(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.index = None
    r = client.post("/api/rag/build")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["count"] >= 1
    assert sess.index is not None


def test_search_409_no_index(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    client.app.state.session.index = None
    r = client.post("/api/rag/search", json={"query": "main"})
    assert r.status_code == 409


def test_search_returns_hits(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.index = None
    client.post("/api/rag/build")
    r = client.post("/api/rag/search", json={"query": "main return", "k": 5})
    assert r.status_code == 200
    hits = r.json()
    assert isinstance(hits, list)
    assert len(hits) >= 1
    for h in hits:
        assert "score" in h
        assert "function" in h
        assert "address" in h["function"]
        assert "name" in h["function"]
        assert "source" in h


def test_search_respects_k(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    client.post("/api/rag/build")
    r = client.post("/api/rag/search", json={"query": "main", "k": 1})
    assert r.status_code == 200
    assert len(r.json()) <= 1


def test_similar_404_unknown_addr(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    client.post("/api/rag/build")
    r = client.post("/api/rag/similar", json={"addr": "0xdeadbeef", "k": 5})
    assert r.status_code == 404


def test_similar_returns_self_at_top(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    client.post("/api/rag/build")
    r = client.post("/api/rag/similar", json={"addr": "0x1000", "k": 5})
    assert r.status_code == 200
    hits = r.json()
    assert hits[0]["function"]["address"] == "0x1000"


def test_similar_409_no_index(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    client.app.state.session.index = None
    r = client.post("/api/rag/similar", json={"addr": "0x1000"})
    assert r.status_code == 409
