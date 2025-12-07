# app/api/routers/count.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.models.enums import MovementType
from app.services.stock_service import StockService

router = APIRouter(prefix="/count", tags=["count"])


# ==========================
# Request / Response models
# ==========================


class CountRequest(BaseModel):
    """
    盘点校正请求（批次级）：
      - 必填：item_id, location_id, qty(绝对量), ref, batch_code
      - 至少提供其一：production_date / expiry_date
      - occurred_at 使用 UTC 时间戳（时区感知），默认当前时间
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    item_id: int = Field(..., description="商品ID")
    location_id: int = Field(..., description="库位ID")
    qty: int = Field(..., ge=0, description="盘点后的实际数量（绝对量）")
    ref: str = Field(..., description="业务参考号（用于台账幂等）")
    batch_code: str = Field(..., description="批次码（猫粮业务必填）")
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="盘点发生时间（UTC）；默认当前时间",
    )
    # 与内核 StockService.adjust 类型保持一致：datetime；至少提供一个
    production_date: Optional[datetime] = Field(None, description="生产日期（可选）")
    expiry_date: Optional[datetime] = Field(None, description="有效期（可选）")

    @model_validator(mode="after")
    def _audit_contract(self) -> "CountRequest":
        if not self.batch_code:
            raise ValueError("猫粮盘点必须提供 batch_code。")
        if self.production_date is None and self.expiry_date is None:
            raise ValueError(
                "猫粮入库/盘点必须提供 production_date 或 expiry_date（至少一项），以支撑 FEFO 管理。"
            )
        # 统一为 UTC 感知时间
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class CountResponse(BaseModel):
    ok: bool = True
    after: int
    ref: str
    item_id: int
    location_id: int
    batch_code: str
    occurred_at: datetime


# ==========================
# Route
# ==========================


@router.post("", response_model=CountResponse, status_code=status.HTTP_200_OK)
async def count_inventory(
    req: CountRequest,
    session: AsyncSession = Depends(get_async_session),
) -> CountResponse:
    """
    将 (item_id, location_id, batch_id[由 batch_code 解析]) 的库存 **校正为** 给定 qty（绝对量）。

    流程：
      1) 通过内核规则幂等解析/创建批次，得到 batch_id（与内核粒度一致）；
      2) 以 (item_id, location_id, batch_id) 精确读取 current qty；
      3) 计算 delta = qty - current，调用 StockService.adjust(reason=COUNT) 落一条台账
         （即使 delta==0 也落账，便于审计）。
    """
    svc = StockService()

    # 1) 解析/幂等建档 → batch_id
    try:
        batch_id = await svc._resolve_batch_id(  # 协作调用，确保与内核粒度一致
            session=session,
            item_id=req.item_id,
            location_id=req.location_id,
            batch_code=req.batch_code,
            production_date=req.production_date,
            expiry_date=req.expiry_date,
            warehouse_id=None,  # 交给内核按 location 推导
            created_at=req.occurred_at,  # 与台账时间源一致
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve batch: {e}",
        )

    # 2) 按批次精确读取 current qty（分支查询，避免 asyncpg 类型歧义）
    if batch_id is None:
        sql = text(
            "SELECT COALESCE(SUM(qty), 0) FROM stocks WHERE item_id=:i AND location_id=:l AND batch_id IS NULL"
        )
        params = {"i": req.item_id, "l": req.location_id}
    else:
        sql = text(
            "SELECT COALESCE(SUM(qty), 0) FROM stocks WHERE item_id=:i AND location_id=:l AND batch_id=:b"
        )
        params = {"i": req.item_id, "l": req.location_id, "b": int(batch_id)}
    current_row = await session.execute(sql, params)
    current = int(current_row.scalar() or 0)

    # 3) 计算 delta 并落 COUNT 台账（即使 delta==0 也落一笔，保证审计留痕）
    delta = int(req.qty) - current
    try:
        res = await svc.adjust(
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
        # 契约/参数类错误
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"count failed: {e}")

    return CountResponse(
        ok=True,
        after=int(res["after"]),
        ref=req.ref,
        item_id=req.item_id,
        location_id=req.location_id,
        batch_code=req.batch_code,
        occurred_at=req.occurred_at,
    )
