"""Call graph construction from BinaryArtifact, with queries and serialization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import networkx as nx  # type: ignore[import-untyped]

from bainary.graph.errors import GraphError
from bainary.lift.artifact import BinaryArtifact


@dataclass(frozen=True)
class FunctionNode:
    """Metadata for a function node in the call graph."""
    address: str
    name: str
    signature: str
    is_external: bool
    is_thunk: bool
    pseudocode: str | None
    size_bytes: int


class CallGraph:
    """A call graph built from a BinaryArtifact.

    Nodes are function addresses; metadata is stored as FunctionNode
    instances accessible via ``cg.functions``. Edges represent calls
    (caller → callee).

    Use the ergonomic methods (callers_of, callees_of, etc.) for common
    queries, or access ``cg.graph`` directly for any NetworkX algorithm.
    """

    def __init__(self, graph: nx.DiGraph) -> None:
        self._graph = graph

    @classmethod
    def from_artifact(cls, artifact: BinaryArtifact) -> CallGraph:
        """Build a call graph from a BinaryArtifact."""
        g = nx.DiGraph()
        for fn in artifact.functions:
            # A function is "external" if it's a thunk (PLT wrapper for an
            # imported function). Note: true imports are not in
            # artifact.functions at all (they're in artifact.imports).
            # A thunk here is a wrapper that the binary defines to
            # forward calls to the import. We mark it external so
            # callers/callees queries can distinguish "internal logic"
            # from "glue to library".
            node = FunctionNode(
                address=fn.address,
                name=fn.name,
                signature=fn.signature,
                is_external=fn.is_thunk,
                is_thunk=fn.is_thunk,
                pseudocode=fn.pseudocode,
                size_bytes=fn.size_bytes,
            )
            g.add_node(fn.address, node=node)
        # Edges to callees not in the graph (e.g. external imports) are
        # dropped — those callees aren't in artifact.functions, so they
        # have no node here. This is by design; the graph is internal-only.
        for fn in artifact.functions:
            for callee in fn.callees:
                if callee.address in g:
                    g.add_edge(fn.address, callee.address)
        return cls(g)

    @classmethod
    def from_json(cls, path: str | Path) -> CallGraph:
        """Build a call graph from a JSON file produced by subsystem A."""
        return cls.from_artifact(BinaryArtifact.from_json(Path(path)))

    @property
    def graph(self) -> nx.DiGraph:
        """The underlying NetworkX DiGraph (for advanced queries)."""
        return self._graph

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()  # type: ignore[no-any-return]

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()  # type: ignore[no-any-return]

    @property
    def functions(self) -> dict[str, FunctionNode]:
        """Mapping of address → FunctionNode for all nodes."""
        return {addr: data["node"] for addr, data in self._graph.nodes(data=True)}

    def _resolve_name(self, name: str) -> str:
        """Resolve a function name to its address.

        Raises GraphError if the name doesn't exist or is duplicated.
        """
        matches = [
            addr for addr, data in self._graph.nodes(data=True)
            if data["node"].name == name
        ]
        if not matches:
            raise GraphError(f"function {name!r} not in graph")
        if len(matches) > 1:
            raise GraphError(
                f"duplicate function name {name!r}: addresses {matches}"
            )
        return matches[0]  # type: ignore[no-any-return]

    def callers_of(self, name: str, *, transitive: bool = False) -> set[str]:
        """Return the set of function names that call ``name``.

        If ``transitive``, includes all transitive callers.
        """
        addr = self._resolve_name(name)
        if transitive:
            ancestors = nx.ancestors(self._graph, addr)
        else:
            ancestors = set(self._graph.predecessors(addr))
        return {self._addr_to_name(a) for a in ancestors}

    def callees_of(self, name: str, *, transitive: bool = False) -> set[str]:
        """Return the set of function names that ``name`` calls.

        If ``transitive``, includes all transitive callees.
        """
        addr = self._resolve_name(name)
        if transitive:
            descendants = nx.descendants(self._graph, addr)
        else:
            descendants = set(self._graph.successors(addr))
        return {self._addr_to_name(a) for a in descendants}

    def orphans(self) -> set[str]:
        """Return the set of function names that nobody calls (no incoming edges)."""
        return {
            self._addr_to_name(addr)
            for addr in self._graph.nodes()
            if self._graph.in_degree(addr) == 0
        }

    def entry_points(self) -> set[str]:
        """Return the set of function names with no callers (same as orphans)."""
        return self.orphans()

    def _addr_to_name(self, addr: str) -> str:
        return self._graph.nodes[addr]["node"].name  # type: ignore[no-any-return]
