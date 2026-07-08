"""FastAPI application factory for the bAInary GUI.

The app serves a static frontend (HTML/JS vanilla + Monaco via CDN) and a
JSON REST API at ``/api/*``. A single :class:`bainary.gui.state.ArtifactSession`
lives on ``app.state.session`` for the lifetime of the process; route
modules import it via :data:`get_session`.

Route registration is intentionally split across small modules in
:mod:`bainary.gui.routes` — each module owns a :class:`fastapi.APIRouter`
covering one concern (binary, functions, graph, refine, rag, settings, meta).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from bainary.gui.state import ArtifactSession

_STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    """Construct the FastAPI application with the static mount and routes."""
    app = FastAPI(
        title="bAInary GUI",
        version="0.1.0",
        description="AI-assisted reverse engineering GUI for bAInary.",
    )

    # One ArtifactSession per process — single-tenant, loopback by default.
    app.state.session = ArtifactSession()

    # Static assets (HTML shell + per-panel JS + CSS). Mount before the
    # root catch-all so the SPA shell loads at /.
    app.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        """Serve the single-page shell."""
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

    # Routers are imported lazily here to keep import time low and avoid
    # circular imports (each router module reads `get_session`).
    from bainary.gui.routes import (  # noqa: WPS433  # local import is intentional
        binary,
        functions,
        graph,
        meta,
        rag,
        refine,
        settings,
    )

    for router in (
        binary.router,
        functions.router,
        graph.router,
        refine.router,
        rag.router,
        settings.router,
        meta.router,
    ):
        app.include_router(router)

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


def get_session(app: FastAPI) -> ArtifactSession:
    """Return the :class:`ArtifactSession` attached to ``app``."""
    sess = app.state.session
    assert isinstance(sess, ArtifactSession)
    return sess


# A module-level app instance is provided so `uvicorn bainary.gui.server:app`
# has a target without forcing callers to call create_app().
app = create_app()
