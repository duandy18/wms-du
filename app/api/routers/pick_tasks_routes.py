# app/api/routers/pick_tasks_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.pick_tasks_routes_commit import register_commit
from app.api.routers.pick_tasks_routes_commit_check import register_commit_check
from app.api.routers.pick_tasks_routes_create import register_create
from app.api.routers.pick_tasks_routes_diff import register_diff
from app.api.routers.pick_tasks_routes_get import register_get
from app.api.routers.pick_tasks_routes_list import register_list
from app.api.routers.pick_tasks_routes_scan import register_scan


def register(router: APIRouter) -> None:
    """
    按功能拆分后的聚合注册入口（硬合同）：

      - create:       POST /from-order/{order_id}
      - list:         GET  /
      - get:          GET  /{task_id}
      - scan:         POST /{task_id}/scan
      - diff:         GET  /{task_id}/diff
      - commit-check: GET  /{task_id}/commit-check      ✅ 只读预检（批次/库存/空提交）
      - commit:       POST /{task_id}/commit
    """
    register_create(router)
    register_list(router)
    register_get(router)
    register_scan(router)
    register_diff(router)

    # ✅ 只读预检：把“批次/库存/空提交”等硬门禁从前端推导中拿回来
    register_commit_check(router)

    register_commit(router)
