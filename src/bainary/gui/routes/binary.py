"""Binary routes — lift (upload/path), info, hex view, function list.

Filled in by Task 5. Browser-facing endpoints live under ``/api/*``.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["binary"])


@router.get("/binary")
async def get_binary() -> dict[str, str]:
    """Stub: real implementation arrives in Task 5."""
    return {"detail": "not loaded yet"}
