# app/api/routers/dev_stock_adjust.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.deps import get_session
from app.models.enums import MovementType
from app.services.stock_service import StockService

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
    # 合同：batch_code 对 shelf-life item 必须合法；对非 shelf-life 必须为 null
    has_map = await fetch_item_has_shelf_life_map(session, {int(payload.item_id)})
    if int(payload.item_id) not in has_map:
        raise HTTPException(status_code=422, detail=f"unknown item_id: {payload.item_id}")
    requires_batch = has_map[int(payload.item_id)] is True
    norm_batch = validate_batch_code_contract(requires_batch=requires_batch, batch_code=payload.batch_code)

    # 对 shelf-life 商品：正向入库/加库存时，必须提供日期（让库存引擎能建 lot）
    if requires_batch and int(payload.delta) > 0:
        if payload.production_date is None or payload.expiry_date is None:
            raise HTTPException(
                status_code=422,
                detail="production_date and expiry_date are required for shelf-life items when delta > 0",
            )

    ts = payload.occurred_at or datetime.now(timezone.utc)

    svc = StockService()
    try:
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
        )
        await session.commit()
        return {"ok": True, "result": res}
    except Exception:
        await session.rollback()
        raise
