# app/api/routers/pick_tasks_routes_create_print.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_422
from app.db.session import get_session
from app.api.routers.pick_tasks_helpers import load_task_with_lines
from app.api.routers.pick_tasks_routes_common import load_latest_pick_list_print_job
from app.api.routers.pick_tasks_schemas import PickTaskOut, PickTaskPrintPickListIn
from app.api.routers.pick_tasks_routes_create_common import enqueue_pick_list_print_job


def register_print(router: APIRouter) -> None:
    @router.post("/{task_id}/print-pick-list", response_model=PickTaskOut)
    async def print_pick_list(
        task_id: int,
        payload: PickTaskPrintPickListIn,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        """
        手工触发打印（显式动作）：
        - 幂等 enqueue pick_list print_job
        - 不做任何自动解析（order_id 必须由调用方显式提供）
        """
        try:
            task = await load_task_with_lines(session, task_id=int(task_id))
            # 构造打印行：只取 req_qty>0 的行
            lines_payload = [
                {"item_id": int(ln.item_id), "req_qty": int(ln.req_qty or 0)}
                for ln in (task.lines or [])
                if int(ln.req_qty or 0) > 0
            ]
            if not lines_payload:
                raise_422(
                    "print_reject",
                    "该拣货任务没有可打印的行（req_qty 全为 0 或为空）。",
                    details=[{"type": "state", "path": "lines", "reason": "empty"}],
                )

            await enqueue_pick_list_print_job(
                session,
                order_id=int(payload.order_id),
                task_id=int(task.id),
                warehouse_id=int(task.warehouse_id),
                lines=lines_payload,
                trace_id=(payload.trace_id or None),
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            raise

        out = PickTaskOut.model_validate(task)
        out.print_job = await load_latest_pick_list_print_job(session, task_id=int(out.id))
        return out
