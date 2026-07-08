"""Function-detail routes — GET /api/functions/{addr}, callers, callees.

Callers/callees are read from the per-function data on the artifact
(field ``callers``/``callees``). A future task can extend these endpoints
to perform transitive traversal via the CallGraph when needed.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path

from bainary.gui.routes._deps import get_session
from bainary.gui.state import ArtifactSession
from bainary.lift.artifact import Function

router = APIRouter(prefix="/api/functions", tags=["functions"])


def _require_artifact(sess: ArtifactSession) -> None:
    if sess.artifact is None:
        raise HTTPException(status_code=409, detail="no artifact loaded; lift a binary first")


def _find_function(sess: ArtifactSession, addr: str) -> Function:
    assert sess.artifact is not None  # guarded by callers
    for f in sess.artifact.functions:
        if f.address == addr:
            return f
    raise HTTPException(status_code=404, detail=f"no function at {addr}")


@router.get("/{addr}")
def get_function(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    addr: str = Path(..., pattern=r"^0x[0-9a-fA-F]+$"),
) -> dict[str, Any]:
    """Return the full :class:`Function` record at ``addr``."""
    _require_artifact(sess)
    fn = _find_function(sess, addr)
    return fn.to_dict()


@router.get("/{addr}/callees")
def get_callees(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    addr: str = Path(..., pattern=r"^0x[0-9a-fA-F]+$"),
) -> list[dict[str, Any]]:
    """List the direct callees of the function at ``addr``."""
    _require_artifact(sess)
    fn = _find_function(sess, addr)
    return [c.to_dict() for c in fn.callees]


@router.get("/{addr}/callers")
def get_callers(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    addr: str = Path(..., pattern=r"^0x[0-9a-fA-F]+$"),
) -> list[dict[str, Any]]:
    """List the direct callers of the function at ``addr``."""
    _require_artifact(sess)
    fn = _find_function(sess, addr)
    return [c.to_dict() for c in fn.callers]
