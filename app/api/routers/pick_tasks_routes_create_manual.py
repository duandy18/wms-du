# app/api/routers/pick_tasks_routes_create_manual.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_422
from app.db.session import get_session
from app.services.pick_task_service import PickTaskService
from app.api.routers.pick_tasks_schemas import PickTaskCreateFromOrder, PickTaskOut
from app.api.routers.pick_tasks_routes_common import load_latest_pick_list_print_job


def register_manual_create(router: APIRouter) -> None:
    async def _create_impl(
        *,
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession,
        require_warehouse: bool,
    ) -> PickTaskOut:
        # ✅ 手工主线：必须显式 warehouse_id
        # ✅ 自动主线：允许 warehouse_id=None，由服务层解析执行仓
        if require_warehouse and payload.warehouse_id is None:
            raise_422(
                "warehouse_required",
                "创建拣货任务必须选择仓库（手工模式）。",
                details=[{"type": "validation", "path": "warehouse_id", "reason": "required"}],
            )

        svc = PickTaskService(session)
        try:
            task = await svc.create_for_order(
                order_id=int(order_id),
                warehouse_id=(int(payload.warehouse_id) if payload.warehouse_id is not None else None),
                source=payload.source,
                priority=payload.priority,
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except ValueError as e:
            await session.rollback()
            raise_422("pick_task_create_reject", str(e))
        except Exception:
            await session.rollback()
            raise

        out = PickTaskOut.model_validate(task)
        out.print_job = await load_latest_pick_list_print_job(session, task_id=int(out.id))
        return out

    @router.post("/manual-from-order/{order_id}", response_model=PickTaskOut)
    async def manual_create_pick_task_from_order(
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        """
        手工入口（推荐）：
        - 必须显式 warehouse_id
        - 只创建 pick_task + lines
        - ❌ 不自动 enqueue 打印
        """
        return await _create_impl(
            order_id=int(order_id),
            payload=payload,
            session=session,
            require_warehouse=True,
        )

    @router.post("/from-order/{order_id}", response_model=PickTaskOut, deprecated=True)
    async def create_pick_task_from_order_compat(
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        """
        兼容入口（deprecated）：
        - 允许不传 warehouse_id（Phase 2：后端解析执行仓）
        - ❌ 不自动化、不自动打印
        """
        return await _create_impl(
            order_id=int(order_id),
            payload=payload,
            session=session,
            require_warehouse=False,
        )
