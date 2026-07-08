"""Routers for the bAInary GUI REST API.

Each module exports a ``router: fastapi.APIRouter`` covering one concern:
binary (lift + hex), functions (detail + callers/callees), graph (full +
focus), refine (SSE progress), rag (build/search/similar), settings
(.env GET/PUT), meta (imports/exports/strings).
"""
