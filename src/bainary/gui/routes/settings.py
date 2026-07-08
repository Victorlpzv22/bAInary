"""Settings routes — GET/PUT /api/settings (persists .env).

Filled in by Task 10.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["settings"])
