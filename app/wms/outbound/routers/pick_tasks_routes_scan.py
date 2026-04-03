# app/wms/outbound/routers/pick_tasks_routes_scan.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.services.lot_code_contract import (
    fetch_item_expiry_policy_map,
    validate_lot_code_contract,
)
from app.core.problem import raise_409, raise_422
from app.db.session import get_session
from app.wms.outbound.services.pick_task_scan import PickTaskScanError
from app.wms.outbound.services.pick_task_service import PickTaskService
from app.wms.outbound.contracts.pick_tasks import PickTaskOut, PickTaskScanIn
from app.wms.outbound.helpers.pick_tasks_routes_common import load_latest_pick_list_print_job


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


def register_scan(router: APIRouter) -> None:
    @router.post("/{task_id}/scan", response_model=PickTaskOut)
    async def record_scan_for_pick_task(
        task_id: int,
        payload: PickTaskScanIn,
        session: AsyncSession = Depends(get_session),
    ) -> PickTaskOut:

        expiry_policy_map = await fetch_item_expiry_policy_map(
            session, {int(payload.item_id)}
        )

        if payload.item_id not in expiry_policy_map:
            raise_422(
                "unknown_item",
                f"未知商品 item_id={payload.item_id}。",
                details=[
                    {
                        "type": "validation",
                        "path": "item_id",
                        "item_id": int(payload.item_id),
                        "reason": "unknown",
                    }
                ],
            )

        requires_batch = _requires_batch_from_expiry_policy(
            expiry_policy_map.get(payload.item_id)
        )

        # ✅ 合同双轨：lot_code 正名 + batch_code 兼容
        lot_code = getattr(payload, "lot_code", None) or payload.batch_code
        batch_code = validate_lot_code_contract(
            requires_batch=requires_batch,
            lot_code=lot_code,
        )

        svc = PickTaskService(session)
        try:
            task = await svc.record_scan(
                task_id=task_id,
                item_id=payload.item_id,
                qty=payload.qty,
                batch_code=batch_code,  # 兼容：内部仍使用 batch_code 字段名
            )
            await session.commit()
        except HTTPException:
            await session.rollback()
            raise
        except PickTaskScanError as e:
            await session.rollback()
            raise_422(
                e.error_code,
                e.message,
                details=list(e.details or []),
            )
        except ValueError as e:
            await session.rollback()
            raise_409(
                "pick_scan_reject",
                str(e),
                details=[{"type": "state", "path": "scan", "reason": str(e)}],
            )
        except Exception:
            await session.rollback()
            raise

        out = PickTaskOut.model_validate(task)
        out.print_job = await load_latest_pick_list_print_job(
            session, task_id=int(out.id)
        )
        return out
