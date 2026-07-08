"""Settings routes — GET/PUT /api/settings.

The server stores its config in ``.env`` at the project root. GET returns
a public (key-masked) view; PUT persists a partial update. After a
successful PUT, the in-process :class:`Refiner` and :class:`Index` are
invalidated so the next request re-creates them with the new settings.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from bainary.gui.config import load_env, save_env
from bainary.gui.routes._deps import get_session
from bainary.gui.state import ArtifactSession

router = APIRouter(prefix="/api", tags=["settings"])

_ALLOWED_KEYS = frozenset(
    {
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "OPENCODE_APIKEY",
        "LIFT_BACKEND",
        "GUI_HOST",
        "GUI_PORT",
    }
)


@router.get("/settings")
def get_settings() -> dict[str, Any]:
    """Return the public (key-masked) view of the current .env settings."""
    s = load_env()
    return s.to_public_dict()


@router.put("/settings")
def put_settings(
    sess: Annotated[ArtifactSession, Depends(get_session)],
    payload: dict[str, Any] = Body(...),  # noqa: B008
) -> dict[str, Any]:
    """Persist a partial update to the .env file.

    Body keys are mapped directly to env-var names. Unknown keys are
    rejected. The current refiner and index are invalidated so the next
    request rebuilds them with the new configuration.
    """
    unknown = set(payload) - _ALLOWED_KEYS
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown settings keys: {sorted(unknown)}",
        )
    # Convert/validate the GUI_PORT if present.
    updates: dict[str, str | None] = {}
    for k, v in payload.items():
        if k == "GUI_PORT":
            try:
                updates[k] = str(int(v))
            except (TypeError, ValueError) as e:
                raise HTTPException(status_code=422, detail=f"GUI_PORT must be int: {e}") from e
        else:
            if v is None or v == "":
                updates[k] = ""
            else:
                updates[k] = str(v)
    save_env(None, updates)
    # Invalidate cached LLM-dependent state; keep artifact/callgraph.
    sess.refiner = None
    sess.index = None
    return load_env().to_public_dict()
