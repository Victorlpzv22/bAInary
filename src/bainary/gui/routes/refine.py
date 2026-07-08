"""Refine routes — POST /api/refine, GET /api/refine/result/{addr}, GET /api/events.

Refinement is per-function. The frontend ``code.js`` panel polls
``/api/refine/result/{addr}`` whenever it receives a ``refine.progress``
event for the active function, so the refined tab updates as the
background job iterates through the batch.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sse_starlette.sse import EventSourceResponse

from bainary.gui.config import load_env
from bainary.gui.routes._deps import get_session
from bainary.gui.sse import SSEBroker
from bainary.gui.state import ArtifactSession, JobStatus
from bainary.lift.artifact import Function
from bainary.refine import Refiner, create_client
from bainary.refine.cache import RefinementCache

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["refine"])


def _require_artifact(sess: ArtifactSession) -> None:
    if sess.artifact is None:
        raise HTTPException(status_code=409, detail="no artifact loaded; lift a binary first")


def _find_function(sess: ArtifactSession, addr: str) -> Function:
    assert sess.artifact is not None
    for f in sess.artifact.functions:
        if f.address == addr:
            return f
    raise HTTPException(status_code=404, detail=f"no function at {addr}")


def _ensure_refiner(sess: ArtifactSession) -> Refiner:
    """Lazily build a :class:`Refiner` from current .env settings.

    The cache lives in the GUI cache dir; on tests we point it at ``/tmp``
    via ``BAINARY_CACHE_DIR`` so we don't pollute ``~/.cache/bainary``.
    """
    if sess.refiner is not None:
        return sess.refiner
    cfg = load_env()
    client = create_client(
        cfg.llm_provider,
        api_key=cfg.api_key or None,
        base_url=cfg.llm_base_url,
        model=cfg.llm_model,
    )
    import os
    from pathlib import Path

    cache_dir = Path(os.environ.get("BAINARY_GUI_CACHE_DIR", "/tmp/bainary-gui-cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = RefinementCache(cache_dir, model=cfg.llm_model)
    sess.refiner = Refiner(client=client, cache=cache)
    return sess.refiner


def _publish(app: Any, event: str, data: dict[str, Any]) -> None:
    broker: SSEBroker | None = getattr(app.state, "sse_broker", None)
    if broker is not None:
        broker.publish(event, data)


# --- POST /api/refine ---


@router.post("/refine")
async def refine_batch(
    request: Request,
    sess: Annotated[ArtifactSession, Depends(get_session)],
    payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Refine a batch of functions in the background.

    Body:
      - ``addresses``: list of addresses to refine (required)
      - ``min_size``: optional override
      - ``skip_thunks``: optional override (default true)
      - ``skip_no_pseudocode``: optional override (default true)
    """
    _require_artifact(sess)
    payload = payload or {}
    addrs = payload.get("addresses")
    if not isinstance(addrs, list) or not addrs:
        raise HTTPException(status_code=422, detail="'addresses' must be a non-empty list")
    jid = uuid.uuid4().hex[:12]
    sess.jobs[jid] = JobStatus(job_id=jid, kind="refine", status="running", total=len(addrs))
    app_ref = request.app
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        _do_refine_batch,
        app_ref,
        jid,
        list(addrs),
        payload.get("min_size"),
        bool(payload.get("skip_thunks", True)),
        bool(payload.get("skip_no_pseudocode", True)),
    )
    return {"job_id": jid}


def _do_refine_batch(
    app: Any,
    jid: str,
    addrs: list[str],
    min_size: int | None,
    skip_thunks: bool,
    skip_no_pseudocode: bool,
) -> None:
    sess: ArtifactSession = app.state.session
    job = sess.jobs.get(jid)
    if job is None:
        return
    try:
        refiner = _ensure_refiner(sess)
    except Exception as e:
        job.status = "error"
        job.log_lines.append(f"refiner init failed: {e}")
        _publish(app, "refine.error", {"detail": str(e)})
        return
    for addr in addrs:
        fn = next(
            (f for f in (sess.artifact.functions if sess.artifact else []) if f.address == addr),
            None,
        )
        if fn is None:
            job.log_lines.append(f"skip: no function at {addr}")
            _publish(
                app, "refine.progress", {"address": addr, "status": "skip", "reason": "no-such-fn"}
            )
            job.progress += 1
            continue
        try:
            refined = refiner.refine_one(
                fn,
                sess.callgraph,
                min_size=min_size,
                skip_thunks=skip_thunks,
                skip_no_pseudocode=skip_no_pseudocode,
            )
        except Exception as e:
            job.log_lines.append(f"{addr} error: {e}")
            _publish(app, "refine.progress", {"address": addr, "status": "error", "reason": str(e)})
            job.progress += 1
            continue
        if refined is None:
            status = "skip"
        else:
            sess.refined_cache[addr] = refined
            status = "ok"
        _publish(app, "refine.progress", {"address": addr, "status": status})
        job.progress += 1
    job.status = "done"
    _publish(app, "refine.done", {"job_id": jid, "count": job.progress})


# --- GET /api/refine/result/{addr} ---


@router.get("/refine/result/{addr}")
def get_refined(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    addr: str = Path(..., pattern=r"^0x[0-9a-fA-F]+$"),
) -> dict[str, str]:
    """Return the refined pseudo-C for ``addr``, or 404 if not yet refined."""
    _require_artifact(sess)
    code = sess.refined_cache.get(addr)
    if code is None:
        raise HTTPException(status_code=404, detail=f"no refined result for {addr}")
    return {"address": addr, "refined": code}


# --- SSE stream ---


@router.get("/events")
async def events(request: Request) -> EventSourceResponse:
    """SSE stream: every connected browser tab receives job progress events."""
    broker: SSEBroker = request.app.state.sse_broker

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        async with broker.subscribe() as q:
            # Send a hello event so the browser knows the connection is live.
            yield {"event": "log", "data": json.dumps({"level": "info", "msg": "connected"})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=15.0)
                except TimeoutError:
                    # heartbeat keeps proxies from closing the connection
                    yield {"event": "ping", "data": "{}"}
                    continue
                yield {
                    "event": evt["event"],
                    "data": json.dumps(evt["data"], default=str),
                }

    return EventSourceResponse(event_gen())
