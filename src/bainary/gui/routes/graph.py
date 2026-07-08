"""Graph routes — full call graph + N-hop focus.

The full-graph endpoint serialises :class:`CallGraph` to
``{nodes:[{id, name, address, is_thunk, is_extern, size_bytes, ...}],
edges:[[from, to], ...]}`` ready for vis-network consumption.

The focus endpoint returns the N-hop ego graph around a node.
"""

from __future__ import annotations

from typing import Annotated, Any

import networkx as nx  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from bainary.graph import CallGraph
from bainary.gui.routes._deps import get_session
from bainary.gui.state import ArtifactSession

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _require_callgraph(sess: ArtifactSession) -> None:
    if sess.artifact is None or sess.callgraph is None:
        raise HTTPException(
            status_code=409,
            detail="no callgraph loaded; lift a binary first",
        )


def _serialise(cg: CallGraph) -> dict[str, list[Any]]:
    nodes: list[dict[str, Any]] = []
    for addr, data in cg.graph.nodes(data=True):
        node = data.get("node")
        if node is None:
            # Defensive: a node without metadata shouldn't exist
            continue
        nodes.append(
            {
                "id": addr,
                "name": node.name,
                "address": node.address,
                "is_thunk": node.is_thunk,
                "is_extern": node.is_external,
                "size_bytes": node.size_bytes,
                "signature": node.signature,
            }
        )
    edges: list[list[str]] = [[u, v] for u, v in cg.graph.edges()]
    return {"nodes": nodes, "edges": edges}


@router.get("")
def full_graph(
    sess: Annotated[ArtifactSession, Depends(get_session)],
) -> dict[str, list[Any]]:
    """Return the full call graph as ``{nodes, edges}``."""
    _require_callgraph(sess)
    assert sess.callgraph is not None
    return _serialise(sess.callgraph)


@router.get("/focus/{addr}")
def focus_graph(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    addr: str = Path(..., pattern=r"^0x[0-9a-fA-F]+$"),
    depth: int = Query(default=1, ge=1, le=10),
) -> dict[str, list[Any]]:
    """Return the N-hop ego graph around ``addr`` (NetworkX ``ego_graph``)."""
    _require_callgraph(sess)
    assert sess.callgraph is not None
    if addr not in sess.callgraph.graph:
        raise HTTPException(status_code=404, detail=f"node {addr} not in callgraph")
    ego: nx.DiGraph = nx.ego_graph(sess.callgraph.graph, addr, radius=depth)
    return _serialise(CallGraph(ego))
