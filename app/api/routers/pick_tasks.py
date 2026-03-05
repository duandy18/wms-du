# app/api/routers/pick_tasks.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import pick_tasks_routes
from app.api.routers.pick_tasks_helpers import load_task_with_lines as _load_task_with_lines
from app.api.routers.pick_tasks_schemas import (
    PickTaskCommitCheckOut,
    PickTaskCommitIn,
    PickTaskCommitResult,
    PickTaskCreateFromOrder,
    PickTaskDiffLineOut,
    PickTaskDiffSummaryOut,
    PickTaskLineOut,
    PickTaskOut,
    PickTaskScanIn,
)

router = APIRouter(prefix="/pick-tasks", tags=["pick-tasks"])


def _register_all_routes() -> None:
    pick_tasks_routes.register(router)


_register_all_routes()

# 兼容：历史 import 可能依赖这些模型/函数名
__all__ = [
    "router",
    "PickTaskLineOut",
    "PickTaskOut",
    "PickTaskCreateFromOrder",
    "PickTaskScanIn",
    "PickTaskCommitIn",
    "PickTaskDiffLineOut",
    "PickTaskDiffSummaryOut",
    "PickTaskCommitResult",
    "PickTaskCommitCheckOut",
    "_load_task_with_lines",
]
