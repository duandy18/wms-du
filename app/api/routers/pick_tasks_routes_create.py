# app/api/routers/pick_tasks_routes_create.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.pick_tasks_routes_create_auto import register_auto_disabled
from app.api.routers.pick_tasks_routes_create_manual import register_manual_create
from app.api.routers.pick_tasks_routes_create_print import register_print


def register_create(router: APIRouter) -> None:
    # 手工主线：显式 warehouse_id
    register_manual_create(router)

    # 自动化入口：保留路由但禁用（明确 422）
    register_auto_disabled(router)

    # 手工触发打印：显式动作
    register_print(router)
