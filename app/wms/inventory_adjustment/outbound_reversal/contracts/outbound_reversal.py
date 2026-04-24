from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


OutboundReversalSourceType = Literal["ORDER", "MANUAL"]


class OutboundReversalOptionsQuery(_Base):
    days: Annotated[int, Field(default=7, ge=1, le=30, description="最近 N 天")]
    limit: Annotated[int, Field(default=100, ge=1, le=200, description="最多返回数量")]
    source_type: OutboundReversalSourceType | None = Field(
        default=None,
        description="来源类型筛选",
    )


class OutboundReversalOptionOut(_Base):
    event_id: Annotated[int, Field(ge=1, description="原出库事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="原出库事件单号")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: OutboundReversalSourceType
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源单号/外部引用号")]
    occurred_at: datetime = Field(description="原出库业务发生时间")
    committed_at: datetime | None = Field(default=None, description="原出库提交时间")
    remark: Annotated[str | None, Field(default=None, max_length=500, description="原事件备注")]
    line_count: Annotated[int, Field(ge=0, description="事件行数")]
    qty_outbound_total: Annotated[int, Field(ge=0, description="原出库总数量")]
    reversible: bool = Field(description="当前是否可冲回")
    non_reversible_reason: str | None = Field(default=None, description="不可冲回原因")


class OutboundReversalOptionsOut(_Base):
    items: list[OutboundReversalOptionOut] = Field(default_factory=list)


class OutboundReversalDetailLineOut(_Base):
    ref_line: Annotated[int, Field(ge=1, description="事件行号")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name_snapshot: str | None = Field(default=None, description="商品名称快照")
    item_sku_snapshot: str | None = Field(default=None, description="SKU 快照")
    item_spec_snapshot: str | None = Field(default=None, description="规格快照")
    qty_outbound: Annotated[int, Field(ge=1, description="原出库数量")]
    lot_id: Annotated[int, Field(ge=1, description="lot_id")]
    lot_code_snapshot: str | None = Field(default=None, description="批次快照")
    order_line_id: int | None = Field(default=None, description="订单行 ID")
    manual_doc_line_id: int | None = Field(default=None, description="手动出库单行 ID")
    remark: str | None = Field(default=None, description="行备注")


class OutboundReversalDetailOut(_Base):
    event_id: Annotated[int, Field(ge=1, description="原出库事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="原出库事件单号")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: OutboundReversalSourceType
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源单号/外部引用号")]
    occurred_at: datetime = Field(description="原出库业务发生时间")
    committed_at: datetime | None = Field(default=None, description="原出库提交时间")
    status: str = Field(description="原事件状态")
    remark: Annotated[str | None, Field(default=None, max_length=500, description="原事件备注")]
    line_count: Annotated[int, Field(ge=0, description="事件行数")]
    qty_outbound_total: Annotated[int, Field(ge=0, description="原出库总数量")]
    reversible: bool = Field(description="当前是否可冲回")
    non_reversible_reason: str | None = Field(default=None, description="不可冲回原因")
    lines: list[OutboundReversalDetailLineOut] = Field(default_factory=list)


class OutboundReversalIn(_Base):
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="冲回业务发生时间",
    )
    operator_name_snapshot: Annotated[str, Field(min_length=1, max_length=64, description="操作人员姓名快照")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="冲回备注")]

    @model_validator(mode="after")
    def _normalize_time(self) -> "OutboundReversalIn":
        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class OutboundReversalRowOut(_Base):
    ref_line: Annotated[int, Field(ge=1, description="事件行号")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    lot_id: Annotated[int, Field(ge=1, description="lot_id")]
    qty_outbound: Annotated[int, Field(ge=1, description="原出库数量")]


class OutboundReversalOut(_Base):
    ok: bool = Field(default=True, description="是否成功")
    event_id: Annotated[int, Field(ge=1, description="冲回事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="冲回事件单号")]
    trace_id: Annotated[str, Field(min_length=1, max_length=128, description="技术链路追踪号")]
    target_event_id: Annotated[int, Field(ge=1, description="被冲回的原事件 ID")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: OutboundReversalSourceType
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源单号/外部引用号")]
    occurred_at: datetime = Field(description="冲回业务发生时间")
    operator_name_snapshot: Annotated[str, Field(min_length=1, max_length=64, description="操作人员姓名快照")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="冲回备注")]
    rows: list[OutboundReversalRowOut] = Field(default_factory=list, description="冲回结果行")


__all__ = [
    "OutboundReversalSourceType",
    "OutboundReversalOptionsQuery",
    "OutboundReversalOptionOut",
    "OutboundReversalOptionsOut",
    "OutboundReversalDetailLineOut",
    "OutboundReversalDetailOut",
    "OutboundReversalIn",
    "OutboundReversalRowOut",
    "OutboundReversalOut",
]
