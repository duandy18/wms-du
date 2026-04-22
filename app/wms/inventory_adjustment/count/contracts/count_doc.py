from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


CountDocStatus = Literal["DRAFT", "FROZEN", "COUNTED", "POSTED", "VOIDED"]


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


# =========================================================
# 出参：lot 快照参考明细
# =========================================================
class CountDocLineLotSnapshotOut(_Base):
    id: int
    lot_id: int
    lot_code_snapshot: Optional[str] = None
    snapshot_qty_base: int
    created_at: datetime


# =========================================================
# 出参：盘点单明细
# =========================================================
class CountDocLineOut(_Base):
    id: int
    line_no: int

    item_id: int
    item_name_snapshot: Optional[str] = None
    item_spec_snapshot: Optional[str] = None

    snapshot_qty_base: int

    counted_item_uom_id: Optional[int] = None
    counted_uom_name_snapshot: Optional[str] = None
    counted_ratio_to_base_snapshot: Optional[int] = None
    counted_qty_input: Optional[int] = None

    counted_qty_base: Optional[int] = None
    diff_qty_base: Optional[int] = None

    reason_code: Optional[str] = None
    disposition: Optional[str] = None
    remark: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    lot_snapshots: List[CountDocLineLotSnapshotOut] = Field(default_factory=list)


# =========================================================
# 出参：盘点单头（含读模型聚合）
# =========================================================
class CountDocOut(_Base):
    id: int
    count_no: str
    warehouse_id: int
    snapshot_at: datetime
    status: CountDocStatus

    posted_event_id: Optional[int] = None
    created_by: Optional[int] = None
    remark: Optional[str] = None

    created_at: datetime
    counted_at: Optional[datetime] = None
    posted_at: Optional[datetime] = None

    # 读模型聚合字段
    line_count: int = 0
    diff_line_count: int = 0
    diff_qty_base_total: int = 0

    # 已过账事件摘要
    posted_event_no: Optional[str] = None
    posted_event_type: Optional[str] = None
    posted_source_type: Optional[str] = None
    posted_event_kind: Optional[str] = None
    posted_event_status: Optional[str] = None


class CountDocDetailOut(CountDocOut):
    lines: List[CountDocLineOut] = Field(default_factory=list)


class CountDocListOut(_Base):
    total: int
    items: List[CountDocOut] = Field(default_factory=list)


# =========================================================
# 入参：创建盘点单
# =========================================================
class CountDocCreateIn(_Base):
    warehouse_id: int = Field(..., ge=1, description="盘点仓库 ID")
    snapshot_at: datetime = Field(..., description="盘点时点（UTC）")
    remark: Optional[str] = Field(default=None, max_length=500, description="备注")

    @field_validator("remark", mode="before")
    @classmethod
    def _trim_remark(cls, v):
        return v.strip() if isinstance(v, str) else v


# =========================================================
# 出参：冻结结果
# =========================================================
class CountDocFreezeOut(_Base):
    doc_id: int
    status: CountDocStatus
    snapshot_at: datetime
    line_count: int
    lot_snapshot_count: int


# =========================================================
# 入参：更新盘点明细（录入实盘数量）
# 约定：
# - 前端只传盘点包装单位 ID 和输入数量
# - counted_uom_name_snapshot / counted_ratio_to_base_snapshot /
#   counted_qty_base / diff_qty_base 由后端按 item_uoms 和 snapshot_qty_base 计算
# =========================================================
class CountDocLineCountPatch(_Base):
    line_id: int = Field(..., ge=1)
    counted_item_uom_id: int = Field(..., ge=1, description="盘点包装单位 ID")
    counted_qty_input: int = Field(..., ge=0, description="按盘点包装单位输入的数量")

    reason_code: Optional[str] = Field(default=None, max_length=32)
    disposition: Optional[str] = Field(default=None, max_length=32)
    remark: Optional[str] = Field(default=None, max_length=255)

    @field_validator("reason_code", "disposition", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v


class CountDocLinesUpdateIn(_Base):
    lines: List[CountDocLineCountPatch] = Field(default_factory=list, min_length=1)


class CountDocLinesUpdateOut(_Base):
    doc_id: int
    status: CountDocStatus
    updated_count: int
    lines: List[CountDocLineOut] = Field(default_factory=list)


# =========================================================
# 出参：过账结果
# =========================================================
class CountDocPostOut(_Base):
    doc_id: int
    status: CountDocStatus
    posted_event_id: int
    posted_at: datetime


__all__ = [
    "CountDocStatus",
    "CountDocLineLotSnapshotOut",
    "CountDocLineOut",
    "CountDocOut",
    "CountDocDetailOut",
    "CountDocListOut",
    "CountDocCreateIn",
    "CountDocFreezeOut",
    "CountDocLineCountPatch",
    "CountDocLinesUpdateIn",
    "CountDocLinesUpdateOut",
    "CountDocPostOut",
]
