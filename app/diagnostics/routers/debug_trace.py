# app/diagnostics/routers/debug_trace.py
from __future__ import annotations

from fastapi import APIRouter

from app.diagnostics.routers import debug_trace_routes

router = APIRouter(prefix="/debug", tags=["debug-trace"])


def _register_all_routes() -> None:
    debug_trace_routes.register(router)


_register_all_routes()

__all__ = ["router"]
