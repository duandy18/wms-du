# app/api/routers/scan_routes_count_commit.py
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.models.enums import MovementType
from app.api.routers.scan_schemas import ScanCountCommitRequest, ScanResponse
from app.services.stock_service import StockService


def register(router: APIRouter) -> None:
    # ==========================
    # /scan/count/commit（legacy → 未来可并入 /scan）
    # ==========================

    @router.post("/scan/count/commit", response_model=ScanResponse, status_code=status.HTTP_200_OK)
    async def scan_count_commit(
        req: ScanCountCommitRequest,
        session: AsyncSession = Depends(get_session),
    ) -> ScanResponse:
        """
        LEGACY：基于 location 的盘点接口。
        当前仍按旧实现工作，未来可迁移到 /scan + ScanRequest(mode='count')，并改用 warehouse_id 粒度。
        """
        svc = StockService()

        # 1) 解析/幂等建档 → batch_id
        try:
            batch_id = await svc._resolve_batch_id(
                session=session,
                item_id=req.item_id,
                location_id=req.location_id,
                batch_code=req.batch_code,
                production_date=req.production_date,
                expiry_date=req.expiry_date,
                warehouse_id=None,
                created_at=req.occurred_at,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"resolve batch failed: {e}")

        # 2) 以 (item,loc,batch_id) 读取 current（分支避免 asyncpg 类型歧义）
        if batch_id is None:
            sql = text(
                "SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i AND location_id=:l AND batch_id IS NULL"
            )
            params = {"i": req.item_id, "l": req.location_id}
        else:
            sql = text(
                "SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i AND location_id=:l AND batch_id=:b"
            )
            params = {"i": req.item_id, "l": req.location_id, "b": int(batch_id)}
        current_row = await session.execute(sql, params)
        current = int(current_row.scalar() or 0)

        # 3) delta = 目标 - 当前；落 COUNT 台账（即使 delta==0 也落，便于审计）
        delta = int(req.qty) - current
        try:
            await svc.adjust(
                session=session,
                item_id=req.item_id,
                location_id=req.location_id,
                delta=delta,
                reason=MovementType.COUNT,
                ref=req.ref,
                ref_line=1,
                occurred_at=req.occurred_at,
                batch_code=req.batch_code,
                production_date=req.production_date,
                expiry_date=req.expiry_date,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"scan(count) failed: {e}")

        scan_ref = f"scan:api:{req.occurred_at.isoformat(timespec='minutes')}"
        return ScanResponse(
            ok=True,
            committed=True,
            scan_ref=scan_ref,
            event_id=None,
            source="scan_count_commit",
            item_id=req.item_id,
            location_id=req.location_id,
            qty=req.qty,
            batch_code=req.batch_code,
        )
