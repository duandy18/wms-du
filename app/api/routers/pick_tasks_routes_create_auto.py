# app/api/routers/pick_tasks_routes_create_auto.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_422
from app.db.session import get_session
from app.api.routers.pick_tasks_schemas import PickTaskCreateFromOrder, PickTaskOut


def register_auto_disabled(router: APIRouter) -> None:
    @router.post("/ensure-from-order/{order_id}", response_model=PickTaskOut)
    async def ensure_pick_task_from_order_disabled(
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        """
        自动化入口：已废弃 / 禁用
        - 不再自动解析仓库
        - 不再自动创建任务
        - 不再自动打印
        """
        _ = (order_id, payload, session)
        raise_422(
            "automation_disabled",
            "自动化入口已禁用：请使用 /pick-tasks/manual-from-order/{order_id} 并显式传 warehouse_id。",
            details=[{"type": "state", "path": "ensure-from-order", "reason": "disabled"}],
        )
