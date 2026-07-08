"""Tests for bainary.gui.routes.functions — GET /api/functions/{addr}.

Callers/callees read from the per-function data on the artifact
(field ``callers``/``callees``); no CallGraph traversal is required for
the basic view. A future task can add transitive traversal via the
CallGraph.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bainary.gui.server import create_app
from bainary.lift.artifact import (
    BasicBlock,
    BinaryArtifact,
    BinaryInfo,
    CallRef,
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
                assembly="push rbp\nmov rbp, rsp\nret",
                is_thunk=False,
                basic_blocks=[
                    BasicBlock(
                        address="0x1000", instructions=[], successors=[], terminator="return"
                    )
                ],
                cfg=Cfg(nodes=["0x1000"], edges=[]),
                callers=[],
                callees=[
                    CallRef.from_dict({"address": "0x2000", "name": "printf", "is_external": True})
                ],
                pseudocode='int main(void) { printf("hi"); return 0; }',
            ),
            Function(
                address="0x1100",
                name="helper",
                signature="void helper(void)",
                calling_convention="cdecl",
                size_bytes=16,
                assembly="nop\nret",
                is_thunk=False,
                basic_blocks=[],
                cfg=Cfg(nodes=[], edges=[]),
                callers=[
                    CallRef.from_dict({"address": "0x1000", "name": "main", "is_external": False})
                ],
                callees=[],
                pseudocode="void helper(void) {}",
            ),
            Function(
                address="0x1200",
                name="_thunk",
                signature="thunk to libc",
                calling_convention="cdecl",
                size_bytes=8,
                assembly="jmp printf",
                is_thunk=True,
                basic_blocks=[],
                cfg=Cfg(nodes=[], edges=[]),
                callers=[],
                callees=[],
                pseudocode=None,
            ),
        ],
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_function_detail_404_no_artifact(client: TestClient) -> None:
    r = client.get("/api/functions/0x1000")
    assert r.status_code == 409


def test_function_detail_404_no_such_address(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/functions/0xdeadbeef")
    assert r.status_code == 404


def test_function_detail_returns_full_record(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/functions/0x1000")
    assert r.status_code == 200
    j = r.json()
    assert j["address"] == "0x1000"
    assert j["name"] == "main"
    assert j["pseudocode"]  # non-empty
    assert j["assembly"]
    assert isinstance(j["basic_blocks"], list)
    assert isinstance(j["cfg"], dict)
    assert isinstance(j["callers"], list)
    assert isinstance(j["callees"], list)
    assert j["is_thunk"] is False
    assert j["callees"][0]["name"] == "printf"


def test_callees_endpoint(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/functions/0x1000/callees")
    assert r.status_code == 200
    cs = r.json()
    assert any(c["name"] == "printf" for c in cs)


def test_callers_endpoint(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/functions/0x1100/callers")
    assert r.status_code == 200
    cs = r.json()
    assert any(c["name"] == "main" for c in cs)


def test_callees_empty_for_thunk(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/functions/0x1200/callees")
    assert r.status_code == 200
    assert r.json() == []


def test_function_detail_thunk_has_no_pseudo(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    r = client.get("/api/functions/0x1200")
    assert r.status_code == 200
    j = r.json()
    assert j["is_thunk"] is True
    assert j["pseudocode"] is None
