# app/schemas/stock.py
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

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
    mode: Literal["NORMAL", "FEFO"] = "NORMAL"
    allow_expired: bool = False
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


class StockBatchQueryIn(_Base):
    item_id: int | None = Field(None, ge=1)
    warehouse_id: int | None = Field(None, ge=1)
    expiry_date_from: date | None = None
    expiry_date_to: date | None = None
    page: Annotated[int, Field(default=1, ge=1)]
    page_size: Annotated[int, Field(default=50, ge=1, le=500)]


class StockBatchRow(_Base):
    batch_id: int
    item_id: int
    warehouse_id: int
    batch_code: str
    production_date: date | None = None
    expiry_date: date | None = None
    qty: int  # ✅ Phase 4B-3: 返回余额数量（来自 stocks_lot 聚合）


class StockBatchQueryOut(_Base):
    total: int
    page: int
    page_size: int
    items: list[StockBatchRow] = Field(default_factory=list)
