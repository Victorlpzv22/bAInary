"""Tests for bainary.graph.CallGraph — unit tests with synthetic artifacts."""

from __future__ import annotations

import pickle

import networkx as nx
import pytest

from bainary.graph import CallGraph, FunctionNode, GraphError
from bainary.lift.artifact import BinaryArtifact


def _fn(
    address: str,
    name: str,
    callees: list[dict] | None = None,
    is_thunk: bool = False,
    pseudocode: str | None = "// stub",
    size_bytes: int = 16,
) -> dict:
    """Build a function dict for _make_artifact."""
    return {
        "address": address,
        "name": name,
        "signature": f"int {name}(void)",
        "calling_convention": "cdecl",
        "size_bytes": size_bytes,
        "is_thunk": is_thunk,
        "basic_blocks": [],
        "cfg": {"nodes": [], "edges": []},
        "callers": [],
        "callees": callees or [],
        "assembly": "ret",
        "pseudocode": pseudocode,
        "pseudocode_error": None,
        "decompiler": "ghidra",
        "stack_frame": {"size": 0, "locals": []},
    }


def _make_artifact(functions: list[dict]) -> BinaryArtifact:
    """Build a synthetic BinaryArtifact from a list of function dicts."""
    return BinaryArtifact.from_dict({
        "schema_version": "1.0",
        "binary": {
            "path": "/tmp/synthetic.elf",
            "sha256": "ab" * 32,
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
    })


def _chain_artifact() -> BinaryArtifact:
    """Artifact with main → a → b → c call chain + printf import."""
    return _make_artifact([
        _fn("0x401000", "main", callees=[{"address": "0x401100", "name": "a", "is_external": False}]),
        _fn("0x401100", "a", callees=[{"address": "0x401200", "name": "b", "is_external": False}]),
        _fn("0x401200", "b", callees=[{"address": "0x401300", "name": "c", "is_external": False}]),
        _fn("0x401300", "c", callees=[]),
        _fn("0x401400", "printf", callees=[], is_thunk=True, pseudocode=None),
    ])


def test_build_from_artifact():
    cg = CallGraph.from_artifact(_chain_artifact())
    assert cg.node_count == 5
    # main → a, a → b, b → c = 3 edges
    assert cg.edge_count == 3


def test_build_from_json(tmp_path):
    artifact = _chain_artifact()
    path = tmp_path / "artifact.json"
    artifact.to_json(path)
    cg = CallGraph.from_json(path)
    assert cg.node_count == 5
    assert cg.edge_count == 3


def test_function_node_metadata():
    cg = CallGraph.from_artifact(_chain_artifact())
    main = cg.functions["0x401000"]
    assert isinstance(main, FunctionNode)
    assert main.name == "main"
    assert main.signature == "int main(void)"
    assert main.is_external is False
    assert main.is_thunk is False
    assert main.pseudocode == "// stub"
    assert main.size_bytes == 16


def test_external_function_marked():
    cg = CallGraph.from_artifact(_chain_artifact())
    printf = cg.functions["0x401400"]
    assert printf.is_external is True
    assert printf.is_thunk is True


def test_empty_artifact():
    cg = CallGraph.from_artifact(_make_artifact([]))
    assert cg.node_count == 0
    assert cg.edge_count == 0
    assert cg.orphans() == set()
    assert cg.entry_points() == set()


def test_graph_attribute_is_nx_digraph():
    import networkx as nx
    cg = CallGraph.from_artifact(_chain_artifact())
    assert isinstance(cg.graph, nx.DiGraph)
    assert cg.graph.number_of_nodes() == 5


def test_callers_of_direct():
    cg = CallGraph.from_artifact(_chain_artifact())
    assert cg.callers_of("a") == {"main"}


def test_callers_of_transitive():
    cg = CallGraph.from_artifact(_chain_artifact())
    assert cg.callers_of("c", transitive=True) == {"main", "a", "b"}


def test_callees_of_direct():
    cg = CallGraph.from_artifact(_chain_artifact())
    assert cg.callees_of("main") == {"a"}


def test_callees_of_transitive():
    cg = CallGraph.from_artifact(_chain_artifact())
    assert cg.callees_of("main", transitive=True) == {"a", "b", "c"}


def test_orphans():
    """Orphans = functions that nobody calls (no incoming edges)."""
    cg = CallGraph.from_artifact(_chain_artifact())
    orphans = cg.orphans()
    assert "main" in orphans
    assert "printf" in orphans
    assert "c" not in orphans


def test_entry_points():
    """Entry points = functions with no callers (same as orphans)."""
    cg = CallGraph.from_artifact(_chain_artifact())
    entries = cg.entry_points()
    assert "main" in entries
    assert "a" not in entries


def test_unknown_function_raises():
    cg = CallGraph.from_artifact(_chain_artifact())
    with pytest.raises(GraphError, match="not in graph"):
        cg.callers_of("nonexistent")


def test_duplicate_names_raise():
    artifact = _make_artifact([
        _fn("0x401000", "foo", callees=[]),
        _fn("0x402000", "foo", callees=[]),
    ])
    cg = CallGraph.from_artifact(artifact)
    with pytest.raises(GraphError, match="duplicate"):
        cg.callers_of("foo")


def _cycle_artifact() -> BinaryArtifact:
    """Artifact with a cycle: a → b → a, plus c → a."""
    return _make_artifact([
        _fn("0x1000", "a", callees=[{"address": "0x2000", "name": "b", "is_external": False}]),
        _fn("0x2000", "b", callees=[{"address": "0x1000", "name": "a", "is_external": False}]),
        _fn("0x3000", "c", callees=[{"address": "0x1000", "name": "a", "is_external": False}]),
    ])


def test_cycles_detects_scc():
    cg = CallGraph.from_artifact(_cycle_artifact())
    cycles = cg.cycles()
    assert len(cycles) == 1
    assert cycles[0] == {"a", "b"}


def test_cycles_no_cycle():
    cg = CallGraph.from_artifact(_chain_artifact())
    assert cg.cycles() == []


def test_shortest_path():
    cg = CallGraph.from_artifact(_chain_artifact())
    path = cg.shortest_path("main", "c")
    assert path == ["main", "a", "b", "c"]


def test_shortest_path_none():
    cg = CallGraph.from_artifact(_chain_artifact())
    # c has no callees, so no path from c to main
    path = cg.shortest_path("c", "main")
    assert path is None


def test_shortest_path_same_node():
    cg = CallGraph.from_artifact(_chain_artifact())
    path = cg.shortest_path("main", "main")
    assert path == ["main"]


def test_to_graphml(tmp_path):
    cg = CallGraph.from_artifact(_chain_artifact())
    path = tmp_path / "graph.graphml"
    cg.to_graphml(path)
    assert path.exists()
    # Verify it's valid XML and readable by NetworkX, and that the
    # FunctionNode fields survive the GraphML round-trip
    loaded = nx.read_graphml(path)
    assert loaded.number_of_nodes() == 5
    assert loaded.number_of_edges() == 3
    main = loaded.nodes["0x401000"]
    assert main["name"] == "main"
    assert main["signature"] == "int main(void)"
    assert main["is_external"] is False
    assert main["is_thunk"] is False
    assert main["size_bytes"] == 16


def test_to_pickle(tmp_path):
    cg = CallGraph.from_artifact(_chain_artifact())
    path = tmp_path / "graph.pkl"
    cg.to_pickle(path)
    assert path.exists()
    loaded = pickle.loads(path.read_bytes())
    assert isinstance(loaded, nx.DiGraph)
    assert loaded.number_of_nodes() == 5
    assert loaded.number_of_edges() == 3
