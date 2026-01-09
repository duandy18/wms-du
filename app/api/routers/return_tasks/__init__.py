# app/api/routers/return_tasks/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from .order_refs import register_order_refs
from .tasks import register_tasks


def build_router() -> APIRouter:
    router = APIRouter(prefix="/return-tasks", tags=["return-tasks"])
    register_order_refs(router)
    register_tasks(router)
    return router


# ✅ 兼容旧导入：app.main.py 仍然可以
# from app.api.routers.return_tasks import router as return_tasks_router
router = build_router()
