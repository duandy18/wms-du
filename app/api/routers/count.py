# app/api/routers/count.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import fetch_item_expiry_policy_map, validate_lot_code_contract
from app.api.deps import get_async_session
from app.models.enums import MovementType
from app.services.stock_service import StockService

router = APIRouter(prefix="/count", tags=["count"])


class CountRequest(BaseModel):
    """
    盘点校正请求（批次级）：

    ✅ 新世界观：
      - 必填：item_id, warehouse_id, qty(绝对量), ref
      - batch_code：按 expiry_policy 语义收紧（Phase M 真相源）
      - production_date / expiry_date：仅对批次商品要求至少其一

    Phase M-4 governance：
      - lot_code 正名；batch_code 兼容别名
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    item_id: int = Field(..., description="商品ID")
    warehouse_id: int = Field(..., ge=1, description="仓库ID")
    qty: int = Field(..., ge=0, description="盘点后的实际数量（绝对量）")
    ref: str = Field(..., description="业务参考号（用于台账幂等）")

    lot_code: Optional[str] = Field(None, description="Lot 展示码（优先使用；等价于 batch_code）")
    batch_code: Optional[str] = Field(None, description="批次码（兼容字段；等价于 lot_code）")

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

    lot_code: Optional[str] = None
    batch_code: Optional[str] = None

    occurred_at: datetime


@router.post("", response_model=CountResponse, status_code=status.HTTP_200_OK)
async def count_inventory(
    req: CountRequest,
    session: AsyncSession = Depends(get_async_session),
) -> CountResponse:
    svc = StockService()

    expiry_policy_map = await fetch_item_expiry_policy_map(session, {int(req.item_id)})
    if req.item_id not in expiry_policy_map:
        raise HTTPException(status_code=422, detail=f"unknown item_id: {req.item_id}")

    requires_batch = str(expiry_policy_map[req.item_id]).upper() == "REQUIRED"
    lot_code = req.lot_code or req.batch_code
    batch_code = validate_lot_code_contract(requires_batch=requires_batch, lot_code=lot_code)

    if requires_batch and req.production_date is None and req.expiry_date is None:
        raise HTTPException(
            status_code=422,
            detail="expiry-policy REQUIRED item requires production_date or expiry_date (at least one).",
        )

    # Phase 4E：读 current 以 lot-world 为准（stocks_lot + lots.lot_code）
    # ✅ psycopg 对 NULL 参数类型推断敏感：显式 CAST(:c AS TEXT)
    cur_sql = text(
        """
        SELECT COALESCE(SUM(s.qty), 0)
          FROM stocks_lot s
          LEFT JOIN lots lo ON lo.id = s.lot_id
         WHERE s.item_id = :i
           AND s.warehouse_id = :w
           AND lo.lot_code IS NOT DISTINCT FROM CAST(:c AS TEXT)
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
        lot_code=batch_code,
        batch_code=batch_code,
        occurred_at=req.occurred_at,
    )
