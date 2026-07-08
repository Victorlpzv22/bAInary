"""Tests for bainary.gui.routes.graph — full graph + N-hop focus."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bainary.graph import CallGraph
from bainary.gui.server import create_app
from bainary.lift.artifact import (
    BinaryArtifact,
    BinaryInfo,
    CallRef,
    ExportRef,
    Function,
    ImportRef,
    Section,
)

FIXTURE = Path("tests/fixtures/loops_elf64/loops.elf")


def _artifact() -> BinaryArtifact:
    fn_main = Function(
        address="0x1000",
        name="main",
        signature="int main(void)",
        calling_convention="cdecl",
        size_bytes=64,
        assembly="",
        is_thunk=False,
        basic_blocks=[],
        cfg=None,
        callers=[],
        callees=[CallRef.from_dict({"address": "0x1100", "name": "helper", "is_external": False})],
    )
    fn_helper = Function(
        address="0x1100",
        name="helper",
        signature="void helper(void)",
        calling_convention="cdecl",
        size_bytes=16,
        assembly="",
        is_thunk=False,
        basic_blocks=[],
        cfg=None,
        callers=[CallRef.from_dict({"address": "0x1000", "name": "main", "is_external": False})],
        callees=[],
    )
    fn_thunk = Function(
        address="0x1200",
        name="plt_printf",
        signature="thunk to printf",
        calling_convention="cdecl",
        size_bytes=8,
        assembly="",
        is_thunk=True,
        basic_blocks=[],
        cfg=None,
        callers=[],
        callees=[],
    )
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
        strings=[],
        functions=[fn_main, fn_helper, fn_thunk],
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_graph_409_no_artifact(client: TestClient) -> None:
    r = client.get("/api/graph")
    assert r.status_code == 409


def test_graph_409_no_callgraph(client: TestClient) -> None:
    client.app.state.session.artifact = _artifact()
    # callgraph is None
    r = client.get("/api/graph")
    assert r.status_code == 409


def test_graph_returns_nodes_and_edges(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.callgraph = CallGraph.from_artifact(sess.artifact)
    r = client.get("/api/graph")
    assert r.status_code == 200
    g = r.json()
    assert "nodes" in g and "edges" in g
    # 3 functions, 1 edge (main -> helper); thunk has no edges
    assert len(g["nodes"]) == 3
    assert len(g["edges"]) == 1
    by_id = {n["id"]: n for n in g["nodes"]}
    assert by_id["0x1000"]["name"] == "main"
    assert by_id["0x1200"]["is_thunk"] is True


def test_graph_focus_409_no_artifact(client: TestClient) -> None:
    r = client.get("/api/graph/focus/0x1000?depth=1")
    assert r.status_code == 409


def test_graph_focus_radius_1_includes_callee(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.callgraph = CallGraph.from_artifact(sess.artifact)
    r = client.get("/api/graph/focus/0x1000?depth=1")
    assert r.status_code == 200
    g = r.json()
    ids = {n["id"] for n in g["nodes"]}
    # radius=1 around main: main + helper (direct callee)
    assert "0x1000" in ids
    assert "0x1100" in ids
    # The unrelated thunk must NOT be in the 1-hop subgraph
    assert "0x1200" not in ids


def test_graph_focus_404_unknown_node(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.callgraph = CallGraph.from_artifact(sess.artifact)
    r = client.get("/api/graph/focus/0xdeadbeef?depth=1")
    assert r.status_code == 404


def test_graph_focus_depth_within_bounds(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.callgraph = CallGraph.from_artifact(sess.artifact)
    r = client.get("/api/graph/focus/0x1000?depth=3")
    assert r.status_code == 200


def test_graph_focus_depth_out_of_bounds_422(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.callgraph = CallGraph.from_artifact(sess.artifact)
    r = client.get("/api/graph/focus/0x1000?depth=11")
    assert r.status_code == 422


def test_graph_node_shape(client: TestClient) -> None:
    sess = client.app.state.session
    sess.artifact = _artifact()
    sess.callgraph = CallGraph.from_artifact(sess.artifact)
    r = client.get("/api/graph")
    g = r.json()
    n = g["nodes"][0]
    for field in ("id", "name", "address", "is_thunk", "is_extern", "size_bytes"):
        assert field in n
