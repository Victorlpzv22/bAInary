"""RAG routes — POST /api/rag/{build,search,similar}.

Filled in by Task 9.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/rag", tags=["rag"])
