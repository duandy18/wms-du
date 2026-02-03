# app/api/routers/pick_tasks_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.pick_tasks_routes_commit import register_commit
from app.api.routers.pick_tasks_routes_create import register_create
from app.api.routers.pick_tasks_routes_diff import register_diff
from app.api.routers.pick_tasks_routes_get import register_get
from app.api.routers.pick_tasks_routes_list import register_list
from app.api.routers.pick_tasks_routes_scan import register_scan


def register(router: APIRouter) -> None:
    """
    按功能拆分后的聚合注册入口：
      - create:  POST /from-order/{order_id}
      - list:    GET  /
      - get:     GET  /{task_id}
      - scan:    POST /{task_id}/scan
      - diff:    GET  /{task_id}/diff
      - commit:  POST /{task_id}/commit
    """
    register_create(router)
    register_list(router)
    register_get(router)
    register_scan(router)
    register_diff(router)
    register_commit(router)
