# app/api/routers/pick_tasks_routes_scan.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.problem import raise_409, raise_422
from app.db.session import get_session
from app.services.pick_task_scan import PickTaskScanError
from app.services.pick_task_service import PickTaskService
from app.api.routers.pick_tasks_schemas import PickTaskOut, PickTaskScanIn
from app.api.routers.pick_tasks_routes_common import load_latest_pick_list_print_job


def register_scan(router: APIRouter) -> None:
    @router.post("/{task_id}/scan", response_model=PickTaskOut)
    async def record_scan_for_pick_task(
        task_id: int,
        payload: PickTaskScanIn,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:
        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, {int(payload.item_id)})
        if payload.item_id not in has_shelf_life_map:
            raise_422(
                "unknown_item",
                f"未知商品 item_id={payload.item_id}。",
                details=[{"type": "validation", "path": "item_id", "item_id": int(payload.item_id), "reason": "unknown"}],
            )

        requires_batch = has_shelf_life_map.get(payload.item_id, False) is True
        batch_code = validate_batch_code_contract(requires_batch=requires_batch, batch_code=payload.batch_code)

        svc = PickTaskService(session)
        try:
            task = await svc.record_scan(
                task_id=task_id,
                item_id=payload.item_id,
                qty=payload.qty,
                batch_code=batch_code,
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except PickTaskScanError as e:
            await session.rollback()
            # ✅ 门禁/业务校验失败：422 Problem（结构化错误合同）
            raise_422(
                e.error_code,
                e.message,
                details=list(e.details or []),
            )
        except ValueError as e:
            await session.rollback()
            # 兜底：未知业务冲突/非法状态等（历史兼容）→ 409 Problem
            raise_409(
                "pick_scan_reject",
                str(e),
                details=[{"type": "state", "path": "scan", "reason": str(e)}],
            )
        except Exception:
            await session.rollback()
            raise

        out = PickTaskOut.model_validate(task)
        out.print_job = await load_latest_pick_list_print_job(session, task_id=int(out.id))
        return out
