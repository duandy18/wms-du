from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CountDocStatus = Literal["DRAFT", "FROZEN", "COUNTED", "POSTED", "VOIDED"]


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


class CountDocExecutionLineOut(_Base):
    id: int
    line_no: int

    item_id: int
    item_name_snapshot: Optional[str] = None
    item_spec_snapshot: Optional[str] = None

    snapshot_qty_base: int

    base_item_uom_id: Optional[int] = None
    base_uom_name: Optional[str] = None

    counted_qty_input: Optional[int] = None
    counted_qty_base: Optional[int] = None
    diff_qty_base: Optional[int] = None


class CountDocExecutionDetailOut(_Base):
    id: int
    count_no: str
    warehouse_id: int
    snapshot_at: datetime
    status: CountDocStatus

    counted_by_name_snapshot: Optional[str] = None
    reviewed_by_name_snapshot: Optional[str] = None

    created_at: datetime
    counted_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None

    line_count: int = 0
    diff_line_count: int = 0
    diff_qty_base_total: int = 0

    lines: List[CountDocExecutionLineOut] = Field(default_factory=list)


__all__ = [
    "CountDocExecutionLineOut",
    "CountDocExecutionDetailOut",
]
