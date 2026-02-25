# app/schemas/stock_lot.py
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class StockLotQueryIn(BaseModel):
    item_id: Optional[int] = Field(None, description="物料ID（可选）")
    warehouse_id: Optional[int] = Field(None, description="仓库ID（可选）")
    lot_id: Optional[int] = Field(None, description="lot_id（可选）")
    qty_nonzero_only: bool = Field(True, description="是否只返回 qty!=0 的行（默认 true）")


class StockLotRow(BaseModel):
    item_id: int
    warehouse_id: int
    lot_id: Optional[int] = None
    lot_code_source: Optional[str] = None
    lot_code: Optional[str] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None
    qty: int


class StockLotQueryOut(BaseModel):
    rows: list[StockLotRow]
