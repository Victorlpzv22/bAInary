"""Refine routes — POST /api/refine, GET /api/refine/result/{addr}, SSE /api/events.

Filled in by Task 8.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["refine"])
