# app/api/routers/scan_routes_count_commit.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.deps import get_session
from app.models.enums import MovementType
from app.api.routers.scan_schemas import ScanCountCommitRequest, ScanResponse
from app.services.stock_service import StockService


def register(router: APIRouter) -> None:
    @router.post("/scan/count/commit", response_model=ScanResponse, status_code=status.HTTP_200_OK)
    async def scan_count_commit(
        req: ScanCountCommitRequest,
        session: AsyncSession = Depends(get_session),
    ) -> ScanResponse:
        """
        盘点提交（warehouse 粒度）。
        """
        svc = StockService()

        has_shelf_life_map = await fetch_item_has_shelf_life_map(session, {int(req.item_id)})
        if req.item_id not in has_shelf_life_map:
            raise HTTPException(status_code=422, detail=f"unknown item_id: {req.item_id}")

        requires_batch = has_shelf_life_map.get(req.item_id, False) is True
        batch_code = validate_batch_code_contract(requires_batch=requires_batch, batch_code=req.batch_code)

        cur_sql = text(
            """
            SELECT COALESCE(SUM(qty), 0)
              FROM stocks
             WHERE item_id=:i
               AND warehouse_id=:w
               AND batch_code IS NOT DISTINCT FROM :c
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
