# app/api/routers/pick_tasks_routes_create.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_422
from app.db.session import get_session
from app.services.pick_task_service import PickTaskService
from app.services.print_jobs_service import enqueue_pick_list_job
from app.api.routers.pick_tasks_schemas import PickTaskCreateFromOrder, PickTaskOut
from app.api.routers.pick_tasks_routes_common import load_latest_pick_list_print_job, load_order_meta_or_404


def register_create(router: APIRouter) -> None:
    @router.post("/from-order/{order_id}", response_model=PickTaskOut)
    async def create_pick_task_from_order(
        order_id: int,
        payload: PickTaskCreateFromOrder,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        if payload.warehouse_id is None:
            raise_422(
                "warehouse_required",
                "创建拣货任务必须选择仓库。",
                details=[{"type": "validation", "path": "warehouse_id", "reason": "required"}],
            )

        svc = PickTaskService(session)
        try:
            task = await svc.create_for_order(
                order_id=order_id,
                warehouse_id=payload.warehouse_id,
                source=payload.source,
                priority=payload.priority,
            )

            # ✅ 幂等 enqueue pick_list print_job（可观测闭环）
            om = await load_order_meta_or_404(session, order_id=int(order_id))
            lines_payload = [
                {"item_id": int(ln.item_id), "req_qty": int(ln.req_qty or 0)}
                for ln in (task.lines or [])
                if int(ln.req_qty or 0) > 0
            ]
            pj_payload = {
                "kind": "pick_list",
                "platform": str(om.get("platform") or "").upper(),
                "shop_id": str(om.get("shop_id") or ""),
                "ext_order_no": str(om.get("ext_order_no") or ""),
                "order_id": int(order_id),
                "pick_task_id": int(task.id),
                "warehouse_id": int(task.warehouse_id),
                "lines": lines_payload,
                "trace_id": om.get("trace_id"),
                "version": 1,
            }
            await enqueue_pick_list_job(session, ref_type="pick_task", ref_id=int(task.id), payload=pj_payload)

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
