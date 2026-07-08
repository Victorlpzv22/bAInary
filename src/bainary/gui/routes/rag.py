"""RAG routes — POST /api/rag/{build,search,similar}.

RAG (subsystem C) uses the local :class:`HashingTextVectorizer` from
:mod:`bainary.rag` — no API key, no network. Build attaches the index
to :class:`ArtifactSession`; subsequent searches reuse it.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from bainary.gui.routes._deps import get_session
from bainary.gui.state import ArtifactSession, JobStatus
from bainary.lift.artifact import Function
from bainary.rag import Index, SearchHit
from bainary.rag.store import InMemoryStore
from bainary.rag.vectorize import HashingTextVectorizer

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["rag"])


def _require_artifact(sess: ArtifactSession) -> None:
    if sess.artifact is None:
        raise HTTPException(status_code=409, detail="no artifact loaded; lift a binary first")


def _require_index(sess: ArtifactSession) -> None:
    if sess.index is None:
        raise HTTPException(status_code=409, detail="index not built; POST /api/rag/build first")


def _hit_to_dict(hit: SearchHit) -> dict[str, Any]:
    return {
        "function": hit.function.to_dict(),
        "binary_sha256": hit.binary_sha256,
        "score": hit.score,
        "source": hit.source,
    }


def _find_function(sess: ArtifactSession, addr: str) -> Function:
    assert sess.artifact is not None
    for f in sess.artifact.functions:
        if f.address == addr:
            return f
    raise HTTPException(status_code=404, detail=f"no function at {addr}")


def _publish(app: Any, event: str, data: dict[str, Any]) -> None:
    from bainary.gui.sse import SSEBroker

    broker: SSEBroker | None = getattr(app.state, "sse_broker", None)
    if broker is not None:
        broker.publish(event, data)


# --- POST /api/rag/build ---


@router.post("/build")
async def build_index(
    request: Request,
    sess: Annotated[ArtifactSession, Depends(get_session)],
) -> dict[str, object]:
    """Build a RAG index over the current artifact (local vectorizer, no API key)."""
    _require_artifact(sess)
    assert sess.artifact is not None
    # InMemoryStore is a single-process, in-RAM store. Persisting to disk
    # is a post-MVP enhancement.
    index = Index(
        vectorizer=HashingTextVectorizer(dim=1024),
        store=InMemoryStore(dim=1024),
    )
    artifact = sess.artifact
    jid = uuid.uuid4().hex[:12]
    sess.jobs[jid] = JobStatus(
        job_id=jid, kind="rag_build", status="running", total=len(artifact.functions)
    )
    # For MVP we build synchronously: the local hashing vectorizer is
    # cheap (a few ms for 100s of functions, seconds for 1000s). The
    # FastAPI thread-pool offload prevents blocking the event loop.
    app_ref = request.app
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, index.add_artifact, artifact)
    sess.index = index
    job = sess.jobs.get(jid)
    if job is not None:
        job.status = "done"
        job.progress = len(artifact.functions)
    _publish(app_ref, "rag_build.done", {"count": len(artifact.functions)})
    return {"job_id": jid, "count": len(artifact.functions)}


# --- POST /api/rag/search ---


@router.post("/search")
def search(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> list[dict[str, Any]]:
    """Run a natural-language search over the indexed functions."""
    _require_artifact(sess)
    _require_index(sess)
    assert sess.index is not None
    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=422, detail="'query' is required")
    k = int(payload.get("k", 10))
    hits = sess.index.search(query, k)
    return [_hit_to_dict(h) for h in hits]


# --- POST /api/rag/similar ---


@router.post("/similar")
def similar(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> list[dict[str, Any]]:
    """Find functions similar to the one at ``addr``."""
    _require_artifact(sess)
    _require_index(sess)
    assert sess.index is not None
    target_addr = (payload.get("addr") or "").strip()
    if not target_addr:
        raise HTTPException(status_code=422, detail="'addr' is required")
    k = int(payload.get("k", 10))
    fn = _find_function(sess, target_addr)
    hits = sess.index.search_similar(fn, k)
    return [_hit_to_dict(h) for h in hits]
