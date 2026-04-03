# app/devtools/routers/dev_stock_adjust.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.wms.shared.services.lot_code_contract import fetch_item_expiry_policy_map, validate_lot_code_contract
from app.models.enums import MovementType
from app.wms.stock.services.stock_service import StockService

router = APIRouter(prefix="/dev", tags=["dev-stock"])


class DevStockAdjustIn(BaseModel):
    warehouse_id: int = Field(..., ge=1)
    item_id: int = Field(..., ge=1)
    delta: int = Field(..., description="库存变化量，正数=加库存，负数=减库存")
    batch_code: Optional[str] = None

    reason: str = Field(default=str(MovementType.RECEIPT))
    ref: str = Field(default="dev:stock_adjust")
    ref_line: int = Field(default=1, ge=1)

    occurred_at: Optional[datetime] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None


@router.post("/stock/adjust")
async def dev_stock_adjust(
    payload: DevStockAdjustIn,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # 合同：batch_code(展示码/旧名) 对 expiry-policy REQUIRED 的商品必须合法；对 NONE 必须为 null
    pol_map = await fetch_item_expiry_policy_map(session, {int(payload.item_id)})
    if int(payload.item_id) not in pol_map:
        raise HTTPException(status_code=422, detail=f"unknown item_id: {payload.item_id}")

    requires_batch = str(pol_map[int(payload.item_id)]).upper() == "REQUIRED"
    norm_batch = validate_lot_code_contract(requires_batch=requires_batch, lot_code=payload.batch_code)

    # 对 REQUIRED 商品：正向入库/加库存时，必须提供日期（让库存引擎能记 receipt 日期事实）
    if requires_batch and int(payload.delta) > 0:
        if payload.production_date is None or payload.expiry_date is None:
            raise HTTPException(
                status_code=422,
                detail="production_date and expiry_date are required for expiry-policy REQUIRED items when delta > 0",
            )

    ts = payload.occurred_at or datetime.now(timezone.utc)

    svc = StockService()
    try:
        # 终态：dev 也不允许绕过 lot 入口；全部走 StockService.adjust（内部确保 supplier/internal lot）
        res = await svc.adjust(
            session=session,
            item_id=int(payload.item_id),
            warehouse_id=int(payload.warehouse_id),
            delta=int(payload.delta),
            reason=str(payload.reason),
            ref=str(payload.ref),
            ref_line=int(payload.ref_line),
            occurred_at=ts,
            batch_code=norm_batch,
            production_date=payload.production_date,
            expiry_date=payload.expiry_date,
            trace_id="dev-stock-adjust",
            meta={"source": "dev_stock_adjust"},
        )
        await session.commit()
        return {"ok": True, "result": res}
    except Exception:
        await session.rollback()
        raise
