"""Graph routes — full call graph + N-hop focus.

Filled in by Task 7.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/graph", tags=["graph"])
