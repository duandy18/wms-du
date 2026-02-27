# app/api/routers/scan_routes_count_commit.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import (
    fetch_item_expiry_policy_map,
    validate_batch_code_contract,
)
from app.api.deps import get_session
from app.models.enums import MovementType
from app.api.routers.scan_schemas import ScanCountCommitRequest, ScanResponse
from app.services.stock_service import StockService


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


def register(router: APIRouter) -> None:
    @router.post("/scan/count/commit", response_model=ScanResponse, status_code=status.HTTP_200_OK)
    async def scan_count_commit(
        req: ScanCountCommitRequest,
        session: AsyncSession = Depends(get_session),
    ) -> ScanResponse:
        """
        盘点提交（warehouse 粒度）。

        Phase M：
        - 策略真相源：items.expiry_policy
        - NONE → batch_code 必须为 null
        - REQUIRED → batch_code 必填
        """

        svc = StockService()

        expiry_policy_map = await fetch_item_expiry_policy_map(session, {int(req.item_id)})
        if req.item_id not in expiry_policy_map:
            raise HTTPException(status_code=422, detail=f"unknown item_id: {req.item_id}")

        requires_batch = _requires_batch_from_expiry_policy(
            expiry_policy_map.get(req.item_id)
        )

        batch_code = validate_batch_code_contract(
            requires_batch=requires_batch,
            batch_code=req.batch_code,
        )

        cur_sql = text(
            """
            SELECT COALESCE(SUM(s.qty), 0)
              FROM stocks_lot s
              LEFT JOIN lots lo ON lo.id = s.lot_id
             WHERE s.item_id=:i
               AND s.warehouse_id=:w
               AND lo.lot_code IS NOT DISTINCT FROM :c
            """
        )
        current_row = await session.execute(
            cur_sql,
            {"i": int(req.item_id), "w": int(req.warehouse_id), "c": batch_code},
        )
        current = int(current_row.scalar() or 0)

        delta = int(req.qty) - current
        try:
            await svc.adjust(
                session=session,
                item_id=req.item_id,
                warehouse_id=req.warehouse_id,
                delta=delta,
                reason=MovementType.COUNT,
                ref=req.ref,
                ref_line=1,
                occurred_at=req.occurred_at,
                batch_code=batch_code,
                production_date=req.production_date,
                expiry_date=req.expiry_date,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"scan(count) failed: {e}")

        scan_ref = f"scan:count:api:{req.occurred_at.isoformat(timespec='minutes')}"

        return ScanResponse(
            ok=True,
            committed=True,
            scan_ref=scan_ref,
            event_id=None,
            source="scan_count_commit",
            item_id=req.item_id,
            warehouse_id=req.warehouse_id,
            qty=req.qty,
            batch_code=batch_code,
        )
