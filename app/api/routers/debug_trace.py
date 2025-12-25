# app/api/routers/debug_trace.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import debug_trace_routes
from app.api.routers.debug_trace_helpers import (
    filter_events_by_warehouse as _filter_events_by_warehouse,
)
from app.api.routers.debug_trace_helpers import infer_movement_type as _infer_movement_type
from app.api.routers.debug_trace_schemas import TraceEventModel, TraceResponseModel

router = APIRouter(prefix="/debug", tags=["debug-trace"])


def _register_all_routes() -> None:
    debug_trace_routes.register(router)


_register_all_routes()

__all__ = [
    "router",
    "TraceEventModel",
    "TraceResponseModel",
    "_infer_movement_type",
    "_filter_events_by_warehouse",
]
