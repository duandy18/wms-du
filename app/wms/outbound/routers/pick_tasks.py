# app/wms/outbound/routers/pick_tasks.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.outbound.routers.pick_tasks_routes import register as register_pick_tasks_routes

router = APIRouter(prefix="/pick-tasks", tags=["pick-tasks"])


def _register_all_routes() -> None:
    register_pick_tasks_routes(router)


_register_all_routes()

__all__ = ["router"]
