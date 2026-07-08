"""Meta routes — imports, exports, strings, per-artifact lookups."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from bainary.gui.routes._deps import get_session
from bainary.gui.state import ArtifactSession
from bainary.lift.artifact import ExportRef, ImportRef, StringRef

router = APIRouter(prefix="/api", tags=["meta"])


def _require_artifact(sess: ArtifactSession) -> None:
    if sess.artifact is None:
        raise HTTPException(status_code=409, detail="no artifact loaded; lift a binary first")


def _filter_imports(items: list[ImportRef], q: str) -> list[dict[str, str]]:
    ql = q.lower()
    out = []
    for i in items:
        if ql and ql not in i.name.lower() and ql not in i.library.lower():
            continue
        out.append({"address": i.address, "name": i.name, "library": i.library})
    return out


def _filter_exports(items: list[ExportRef], q: str) -> list[dict[str, str]]:
    ql = q.lower()
    out = []
    for e in items:
        if ql and ql not in e.name.lower():
            continue
        out.append({"address": e.address, "name": e.name})
    return out


def _filter_strings(items: list[StringRef], q: str) -> list[dict[str, str]]:
    ql = q.lower()
    out = []
    for s in items:
        if ql and ql not in s.value.lower():
            continue
        out.append({"address": s.address, "value": s.value, "encoding": s.encoding})
    return out


@router.get("/imports")
def get_imports(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    q: str = Query(default=""),
) -> list[dict[str, str]]:
    _require_artifact(sess)
    assert sess.artifact is not None
    return _filter_imports(sess.artifact.imports, q)


@router.get("/exports")
def get_exports(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    q: str = Query(default=""),
) -> list[dict[str, str]]:
    _require_artifact(sess)
    assert sess.artifact is not None
    return _filter_exports(sess.artifact.exports, q)


@router.get("/strings")
def get_strings(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    q: str = Query(default=""),
) -> list[dict[str, str]]:
    _require_artifact(sess)
    assert sess.artifact is not None
    return _filter_strings(sess.artifact.strings, q)
