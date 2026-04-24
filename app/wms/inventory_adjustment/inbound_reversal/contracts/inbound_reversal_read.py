from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.wms.inbound.contracts.inbound_commit import InboundSourceType


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundReversalOptionOut(_Base):
    event_id: Annotated[int, Field(ge=1, description="原入库事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="原入库事件单号")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: InboundSourceType
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源引用")]
    occurred_at: datetime = Field(description="业务发生时间")
    committed_at: datetime | None = Field(default=None, description="提交时间")
    remark: Annotated[str | None, Field(default=None, max_length=500, description="备注")]
    line_count: Annotated[int, Field(ge=0, description="事件行数")]
    qty_base_total: Annotated[int, Field(ge=0, description="base 数量合计")]
    reversible: bool = Field(default=True, description="当前是否允许冲回")
    non_reversible_reason: Annotated[str | None, Field(default=None, max_length=255, description="不可冲回原因")]


class InboundReversalOptionsOut(_Base):
    items: list[InboundReversalOptionOut] = Field(default_factory=list, description="候选事件列表")


class InboundReversalDetailLineOut(_Base):
    line_no: Annotated[int, Field(ge=1, description="事件行号")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="商品名快照")]
    item_spec_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="规格快照")]
    actual_uom_id: Annotated[int, Field(ge=1, description="实际单位 ID")]
    actual_uom_name_snapshot: Annotated[str | None, Field(default=None, max_length=64, description="实际单位名快照")]
    actual_qty_input: Annotated[int, Field(ge=1, description="实际输入数量")]
    actual_ratio_to_base_snapshot: Annotated[int, Field(ge=1, description="实际单位换算比快照")]
    qty_base: Annotated[int, Field(ge=1, description="base 数量")]
    lot_id: Annotated[int | None, Field(default=None, description="lot_id")]
    lot_code_input: Annotated[str | None, Field(default=None, max_length=128, description="批次号输入")]
    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日期")
    remark: Annotated[str | None, Field(default=None, max_length=255, description="行备注")]


class InboundReversalDetailOut(_Base):
    event_id: Annotated[int, Field(ge=1, description="原入库事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="原入库事件单号")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: InboundSourceType
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源引用")]
    occurred_at: datetime = Field(description="业务发生时间")
    committed_at: datetime | None = Field(default=None, description="提交时间")
    status: Annotated[str, Field(min_length=1, max_length=32, description="当前状态")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="备注")]
    line_count: Annotated[int, Field(ge=0, description="事件行数")]
    qty_base_total: Annotated[int, Field(ge=0, description="base 数量合计")]
    reversible: bool = Field(default=True, description="当前是否允许冲回")
    non_reversible_reason: Annotated[str | None, Field(default=None, max_length=255, description="不可冲回原因")]
    lines: list[InboundReversalDetailLineOut] = Field(default_factory=list, description="事件行明细")


__all__ = [
    "InboundReversalOptionOut",
    "InboundReversalOptionsOut",
    "InboundReversalDetailLineOut",
    "InboundReversalDetailOut",
]
