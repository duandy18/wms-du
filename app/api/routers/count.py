# app/api/routers/count.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import fetch_item_has_shelf_life_map, validate_batch_code_contract
from app.api.deps import get_async_session
from app.models.enums import MovementType
from app.services.stock_service import StockService

router = APIRouter(prefix="/count", tags=["count"])


class CountRequest(BaseModel):
    """
    盘点校正请求（批次级）：

    ✅ 新世界观：
      - 必填：item_id, warehouse_id, qty(绝对量), ref
      - batch_code：按 has_shelf_life 语义收紧（同旧合同）
      - production_date / expiry_date：仅对批次商品要求至少其一
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    item_id: int = Field(..., description="商品ID")
    warehouse_id: int = Field(..., ge=1, description="仓库ID")
    qty: int = Field(..., ge=0, description="盘点后的实际数量（绝对量）")
    ref: str = Field(..., description="业务参考号（用于台账幂等）")

    batch_code: Optional[str] = Field(None, description="批次码（批次语义由 API 合同层判定）")

    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="盘点发生时间（UTC）；默认当前时间",
    )
    production_date: Optional[datetime] = Field(None, description="生产日期（可选）")
    expiry_date: Optional[datetime] = Field(None, description="有效期（可选）")

    @model_validator(mode="after")
    def _normalize_time(self) -> "CountRequest":
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class CountResponse(BaseModel):
    ok: bool = True
    after: int
    ref: str
    item_id: int
    warehouse_id: int
    batch_code: Optional[str]
    occurred_at: datetime


@router.post("", response_model=CountResponse, status_code=status.HTTP_200_OK)
async def count_inventory(
    req: CountRequest,
    session: AsyncSession = Depends(get_async_session),
) -> CountResponse:
    svc = StockService()

    has_shelf_life_map = await fetch_item_has_shelf_life_map(session, {int(req.item_id)})
    if req.item_id not in has_shelf_life_map:
        raise HTTPException(status_code=422, detail=f"unknown item_id: {req.item_id}")

    requires_batch = has_shelf_life_map.get(req.item_id, False) is True
    batch_code = validate_batch_code_contract(requires_batch=requires_batch, batch_code=req.batch_code)

    if requires_batch and req.production_date is None and req.expiry_date is None:
        raise HTTPException(
            status_code=422,
            detail="shelf-life controlled item requires production_date or expiry_date (at least one).",
        )

    # 读 current：以 (item_id, warehouse_id, batch_code|NULL) 定位
    cur_sql = text(
        """
        SELECT COALESCE(SUM(qty), 0)
          FROM stocks
         WHERE item_id=:i
           AND warehouse_id=:w
           AND batch_code IS NOT DISTINCT FROM :c
        """
    )
    current_row = await session.execute(cur_sql, {"i": int(req.item_id), "w": int(req.warehouse_id), "c": batch_code})
    current = int(current_row.scalar() or 0)

    delta = int(req.qty) - current

    try:
        res = await svc.adjust(
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
        raise HTTPException(status_code=500, detail=f"count failed: {e}")

    return CountResponse(
        ok=True,
        after=int(res["after"]),
        ref=req.ref,
        item_id=req.item_id,
        warehouse_id=req.warehouse_id,
        batch_code=batch_code,
        occurred_at=req.occurred_at,
    )
