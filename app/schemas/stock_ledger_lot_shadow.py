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


class LedgerDateViolationRow(_Base):
    """
    Phase 3 ledger-only:

    lots 已不再承载日期字段；日期 canonical 仅存在于 stock_ledger(RECEIPT)。
    因此这里不再做 ledger vs lots 的 mismatch，而是提供 ledger 自身的“违规/污染”清单：

    - 非 RECEIPT 行携带 production_date/expiry_date（理论上被 DB 约束禁止，正常应为 0）
    """

    ledger_id: int
    lot_id: int
    reason_canon: Optional[str] = None
    production_date: Optional[str] = None
    expiry_date: Optional[str] = None
    occurred_at: datetime


class LotShadowReconcileOut(_Base):
    warehouse_id: int
    item_id: int
    time_from: datetime
    time_to: datetime

    coverage: LotShadowCoverage = Field(default_factory=LotShadowCoverage)
    by_lot: List[LotShadowAggRow] = Field(default_factory=list)

    violation_count: int = 0
    violations: List[LedgerDateViolationRow] = Field(default_factory=list)
