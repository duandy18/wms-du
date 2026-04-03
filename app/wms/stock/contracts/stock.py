# app/wms/stock/contracts/stock.py
from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MovementType

class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

class StockAdjustIn(_Base):
    item_id: Annotated[int, Field(ge=1)]
    warehouse_id: Annotated[int, Field(ge=1)]
    delta: Annotated[int, Field(description="库存变动量；正数入库，负数出库")]
    reason: Annotated[str | None, Field(None, max_length=200)] = None
    ref: Annotated[str | None, Field(None, max_length=128)] = None
    allow_negative: bool = False
    batch_code: Annotated[str | None, Field(None, max_length=100)] = None
    production_date: date | None = None
    expiry_date: date | None = None

    # ✅ Phase M-5+（执行域收口）：
    # - mode/allow_expired 不再作为执行入口；
    # - 过期放行属于“分析/风控”或“人工审核策略”，不属于 adjust API 的隐含开关。
    movement_type: MovementType = MovementType.ADJUSTMENT

    @field_validator("delta")
    @classmethod
    def _nonzero(cls, v: int):
        if v == 0:
            raise ValueError("delta 不能为 0")
        return v

class StockAdjustOut(_Base):
    item_id: int
    warehouse_id: int
    before_quantity: int
    delta: int
    new_quantity: int
    movement_type: MovementType = MovementType.ADJUSTMENT
    applied: bool = True
    message: str = "OK"

class StockRow(_Base):
    item_id: int
    warehouse_id: int
    batch_code: str | None = None
    quantity: int

class StockSummary(_Base):
    item_id: int
    on_hand: int

class StockQueryOut(_Base):
    rows: list[StockRow] = Field(default_factory=list)
    summary: list[StockSummary] = Field(default_factory=list)

__all__ = [
    "StockAdjustIn",
    "StockAdjustOut",
    "StockRow",
    "StockSummary",
    "StockQueryOut",
]
