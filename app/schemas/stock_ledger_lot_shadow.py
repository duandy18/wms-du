# app/schemas/stock_ledger_lot_shadow.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore", populate_by_name=True)


class LotShadowCoverage(_Base):
    total_rows: int = 0
    rows_with_lot: int = 0
    receipt_rows: int = 0
    receipt_rows_with_lot: int = 0

    @property
    def lot_coverage_pct(self) -> float:
        return (self.rows_with_lot / self.total_rows * 100.0) if self.total_rows else 0.0

    @property
    def receipt_lot_coverage_pct(self) -> float:
        return (self.receipt_rows_with_lot / self.receipt_rows * 100.0) if self.receipt_rows else 0.0


class LotShadowAggRow(_Base):
    lot_id: Optional[int] = None
    row_count: int
    sum_delta: int
    first_occurred_at: Optional[datetime] = None
    last_occurred_at: Optional[datetime] = None


class LotShadowDateMismatchRow(_Base):
    ledger_id: int
    lot_id: int
    ledger_production_date: Optional[str] = None
    lot_production_date: Optional[str] = None
    ledger_expiry_date: Optional[str] = None
    lot_expiry_date: Optional[str] = None
    occurred_at: datetime


class LotShadowReconcileOut(_Base):
    warehouse_id: int
    item_id: int
    batch_code_key: Optional[str] = None
    time_from: datetime
    time_to: datetime

    coverage: LotShadowCoverage = Field(default_factory=LotShadowCoverage)
    by_lot: List[LotShadowAggRow] = Field(default_factory=list)

    mismatch_count: int = 0
    mismatches: List[LotShadowDateMismatchRow] = Field(default_factory=list)
