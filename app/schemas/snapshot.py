from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class SnapshotRunResult(BaseModel):
    date: date
    affected_rows: int = 0


class StockSnapshotRead(BaseModel):
    snapshot_date: date
    warehouse_id: int
    location_id: int
    item_id: int
    batch_id: int | None = None
    qty_on_hand: int
    qty_allocated: int
    qty_available: int
    expiry_date: date | None = None
    age_days: int | None = None
    created_at: datetime | None = None

    # ✅ Pydantic v2 写法，替代旧的 class Config
    model_config = ConfigDict(from_attributes=True)


class TrendPoint(BaseModel):
    snapshot_date: date
    qty_on_hand: int
    qty_available: int
