from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class InventoryExplainIn(_Base):
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]

    lot_id: Optional[int] = Field(default=None, ge=1, description="优先 lot_id 作为结构锚点")
    lot_code: Optional[str] = Field(
        default=None,
        max_length=64,
        description="兼容展示码；无批次 INTERNAL lot 传 null",
    )

    limit: Annotated[int, Field(ge=1, le=500)] = 100

    @field_validator("lot_code", mode="before")
    @classmethod
    def _trim_lot_code(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class InventoryExplainAnchor(_Base):
    item_id: int
    item_name: str

    warehouse_id: int
    warehouse_name: str

    lot_id: int
    lot_code: Optional[str] = None

    base_item_uom_id: Optional[int] = None
    base_uom_name: Optional[str] = None

    current_qty: int


class InventoryExplainLedgerRow(_Base):
    id: int

    occurred_at: datetime
    created_at: datetime

    reason: str
    reason_canon: Optional[str] = None
    sub_reason: Optional[str] = None

    ref: str
    ref_line: int

    delta: int
    after_qty: int

    trace_id: Optional[str] = None
    movement_type: Optional[str] = None

    item_id: int
    item_name: Optional[str] = None

    warehouse_id: int

    lot_id: Optional[int] = None
    lot_code: Optional[str] = None

    base_item_uom_id: Optional[int] = None
    base_uom_name: Optional[str] = None


class InventoryExplainSummary(_Base):
    row_count: int
    truncated: bool = False

    current_qty: int
    ledger_last_after_qty: Optional[int] = None
    matches_current: Optional[bool] = None


class InventoryExplainOut(_Base):
    anchor: InventoryExplainAnchor
    ledger_rows: list[InventoryExplainLedgerRow] = Field(default_factory=list)
    summary: InventoryExplainSummary
