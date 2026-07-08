"""Function-detail routes — GET /api/functions/{addr}, callers, callees.

Filled in by Task 6.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/functions", tags=["functions"])
