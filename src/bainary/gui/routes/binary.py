"""Binary routes — lift (upload/path), info, hex view, function list.

These are the only routes that touch subsystems A and C directly. Lift
runs in a background task on the FastAPI event loop's executor so the
server stays responsive while Ghidra is working. The resulting artifact
and its call graph populate :class:`ArtifactSession`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from bainary.graph import CallGraph
from bainary.gui.state import ArtifactSession, JobStatus
from bainary.lift.api import lift as _lift

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["binary"])


def get_session(request: Request) -> ArtifactSession:
    """Return the per-process ArtifactSession (route-local dependency)."""
    sess = request.app.state.session
    assert isinstance(sess, ArtifactSession)
    return sess


def _require_artifact(sess: ArtifactSession) -> None:
    if sess.artifact is None:
        raise HTTPException(status_code=409, detail="no artifact loaded; lift a binary first")


def _job_id() -> str:
    return uuid.uuid4().hex[:12]


def _publish(app: Any, event: str, data: dict[str, Any]) -> None:
    """Best-effort: hand the event to the SSE broker if one is installed."""
    broker = getattr(app.state, "sse_broker", None)
    if broker is not None:
        broker.publish(event, data)


# --- lift ---


@router.post("/lift/path", status_code=200)
async def lift_path(
    payload: dict[str, str],
    request: Request,
    sess: Annotated[ArtifactSession, Depends(get_session)],
) -> dict[str, str]:
    """Lift the binary at ``payload['path']`` using ``payload['backend']``."""
    path = Path(payload.get("path", "").strip())
    backend = payload.get("backend", "ghidra_headless").strip() or "ghidra_headless"
    if not path.exists():
        raise HTTPException(status_code=422, detail=f"path does not exist: {path}")
    if backend == "ghidra_headless" and not os.environ.get("GHIDRA_HOME"):
        raise HTTPException(
            status_code=503,
            detail="Ghidra is not configured; set GHIDRA_HOME or use backend=lief_capstone",
        )
    jid = _job_id()
    sess.jobs[jid] = JobStatus(job_id=jid, kind="lift", status="running")
    app_ref = request.app
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _do_lift_sync, app_ref, jid, path, backend)
    return {"job_id": jid}


@router.post("/lift/upload", status_code=200)
async def lift_upload(
    request: Request,
    sess: Annotated[ArtifactSession, Depends(get_session)],
    file: Annotated[UploadFile, File(...)],
    backend: str = Query(default="ghidra_headless"),
) -> dict[str, str]:
    """Upload a binary file, then lift it asynchronously."""
    if backend == "ghidra_headless" and not os.environ.get("GHIDRA_HOME"):
        raise HTTPException(
            status_code=503,
            detail="Ghidra is not configured; set GHIDRA_HOME or use backend=lief_capstone",
        )
    suffix = Path(file.filename or "").suffix or ".elf"
    tmp = Path(tempfile.mkstemp(suffix=suffix, prefix="bainary-upload-")[1])
    tmp.write_bytes(file.file.read())
    jid = _job_id()
    sess.jobs[jid] = JobStatus(job_id=jid, kind="lift", status="running")
    app_ref = request.app
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _do_lift_sync, app_ref, jid, tmp, backend)
    return {"job_id": jid}


def _do_lift_sync(app: Any, jid: str, path: Path, backend: str) -> None:
    """Synchronous worker: lift the binary and update the session."""
    sess: ArtifactSession = app.state.session
    job = sess.jobs.get(jid)
    if job is None:
        return
    try:
        artifact = _lift(path, backend=backend)
        cg = CallGraph.from_artifact(artifact)
        sess.artifact = artifact
        sess.callgraph = cg
        sess.binary_bytes = None
        sess.refined_cache.clear()
        job.status = "done"
        job.progress = 1
        job.total = 1
        _publish(app, "lift.done", {"functions_count": len(artifact.functions)})
    except ValueError as e:
        job.status = "error"
        job.log_lines.append(str(e))
        _publish(app, "lift.error", {"detail": str(e)})
    except Exception as e:
        job.status = "error"
        job.log_lines.append(f"{type(e).__name__}: {e}")
        _publish(app, "lift.error", {"detail": f"{type(e).__name__}: {e}"})


# --- info ---


@router.get("/binary")
def get_binary(sess: Annotated[ArtifactSession, Depends(get_session)]) -> dict[str, Any]:
    """Return the lifted :class:`BinaryInfo` plus a small summary."""
    _require_artifact(sess)
    assert sess.artifact is not None
    b = sess.artifact.binary
    return {
        "path": b.path,
        "sha256": b.sha256,
        "format": b.format,
        "arch": b.arch,
        "endianness": b.endianness,
        "entry_point": b.entry_point,
        "base_address": b.base_address,
        "decompiler_version": b.decompiler_version,
        "functions_count": len(sess.artifact.functions),
        "sections_count": len(sess.artifact.sections),
        "imports_count": len(sess.artifact.imports),
        "exports_count": len(sess.artifact.exports),
        "strings_count": len(sess.artifact.strings),
    }


# --- hex ---


@router.get("/hex")
def get_hex(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    addr: str = Query(default="0x0", pattern=r"^0x[0-9a-fA-F]+$"),
    length: int = Query(default=256, ge=1, le=65536),
) -> dict[str, Any]:
    """Return hex rows (16 bytes per row) starting at ``addr``."""
    _require_artifact(sess)
    assert sess.artifact is not None
    raw = sess.binary_bytes
    if raw is None:
        path = Path(sess.artifact.binary.path)
        if not path.exists():
            raise HTTPException(
                status_code=410,
                detail=(
                    f"binary file not available at {path}; re-lift or use "
                    f"per-instruction bytes via /api/functions/{{addr}}"
                ),
            )
        raw = path.read_bytes()
        sess.binary_bytes = raw
    start = int(addr, 16)
    end = min(start + length, len(raw))
    chunk = raw[start:end]
    rows: list[dict[str, str]] = []
    for i in range(0, len(chunk), 16):
        row = chunk[i : i + 16]
        off = f"{(start + i):08x}"
        hex_col = " ".join(f"{b:02x}" for b in row)
        ascii_col = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        rows.append({"off": off, "hex": hex_col, "ascii": ascii_col})
    return {"addr": addr, "length": length, "rows": rows}


# --- functions list ---


@router.get("/functions")
def list_functions(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    q: str = Query(default=""),
    limit: int = Query(default=2000, ge=1, le=20000),
) -> list[dict[str, Any]]:
    """Return the list of functions (optionally filtered by substring)."""
    _require_artifact(sess)
    assert sess.artifact is not None
    ql = q.lower()
    out: list[dict[str, Any]] = []
    for f in sess.artifact.functions:
        if ql and ql not in f.name.lower():
            continue
        out.append(
            {
                "address": f.address,
                "name": f.name,
                "is_thunk": f.is_thunk,
                "size_bytes": f.size_bytes,
                "is_extern": any(c.is_external for c in f.callees) and not f.basic_blocks,
            }
        )
        if len(out) >= limit:
            break
    return out


# --- job status ---


@router.get("/jobs/{job_id}")
def job_status(
    job_id: str,
    sess: Annotated[ArtifactSession, Depends(get_session)],
) -> dict[str, Any]:
    job = sess.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return {
        "job_id": job.job_id,
        "kind": job.kind,
        "status": job.status,
        "progress": job.progress,
        "total": job.total,
        "log_lines": list(job.log_lines[-50:]),
    }
