from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.wms.inventory_adjustment.count.contracts.count_doc_execution import (
    CountDocExecutionLineOut,
)


CountDocStatus = Literal["DRAFT", "FROZEN", "COUNTED", "POSTED", "VOIDED"]


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


class CountDocOut(_Base):
    id: int
    count_no: str
    warehouse_id: int
    snapshot_at: datetime
    status: CountDocStatus

    posted_event_id: Optional[int] = None
    created_by: Optional[int] = None

    counted_by_name_snapshot: Optional[str] = None
    reviewed_by_name_snapshot: Optional[str] = None

    remark: Optional[str] = None

    created_at: datetime
    counted_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None

    line_count: int = 0
    diff_line_count: int = 0
    diff_qty_base_total: int = 0

    posted_event_no: Optional[str] = None
    posted_event_type: Optional[str] = None
    posted_source_type: Optional[str] = None
    posted_event_kind: Optional[str] = None
    posted_event_status: Optional[str] = None


class CountDocListOut(_Base):
    total: int
    items: List[CountDocOut] = Field(default_factory=list)


class CountDocCreateIn(_Base):
    warehouse_id: int = Field(..., ge=1, description="盘点仓库 ID")
    snapshot_at: datetime = Field(..., description="盘点时点（UTC）")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")

    @field_validator("remark", mode="before")
    @classmethod
    def _trim_remark(cls, v):
        return v.strip() if isinstance(v, str) else v


class CountDocFreezeOut(_Base):
    doc_id: int
    status: CountDocStatus
    snapshot_at: datetime
    line_count: int
    lot_snapshot_count: int


class CountDocLineCountPatch(_Base):
    line_id: int = Field(..., ge=1)
    counted_qty_input: int = Field(..., ge=0, description="按基础单位输入的盘点数量")


class CountDocLinesUpdateIn(_Base):
    counted_by_name_snapshot: str = Field(..., max_length=128)
    lines: List[CountDocLineCountPatch] = Field(default_factory=list, min_length=1)

    @field_validator("counted_by_name_snapshot", mode="before")
    @classmethod
    def _trim_counted_by(cls, v):
        return v.strip() if isinstance(v, str) else v


class CountDocLinesUpdateOut(_Base):
    doc_id: int
    status: CountDocStatus
    updated_count: int
    lines: List[CountDocExecutionLineOut] = Field(default_factory=list)


class CountDocPostIn(_Base):
    reviewed_by_name_snapshot: str = Field(..., max_length=128)

    @field_validator("reviewed_by_name_snapshot", mode="before")
    @classmethod
    def _trim_reviewed_by(cls, v):
        return v.strip() if isinstance(v, str) else v


class CountDocPostOut(_Base):
    doc_id: int
    status: CountDocStatus
    posted_event_id: int
    posted_at: datetime


class CountDocVoidOut(_Base):
    doc_id: int
    status: CountDocStatus


__all__ = [
    "CountDocStatus",
    "CountDocOut",
    "CountDocListOut",
    "CountDocCreateIn",
    "CountDocFreezeOut",
    "CountDocLineCountPatch",
    "CountDocLinesUpdateIn",
    "CountDocLinesUpdateOut",
    "CountDocPostIn",
    "CountDocPostOut",
    "CountDocVoidOut",
]
