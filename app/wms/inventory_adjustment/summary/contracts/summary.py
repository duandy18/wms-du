from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


InventoryAdjustmentSummaryType = Literal[
    "COUNT",
    "INBOUND_REVERSAL",
    "OUTBOUND_REVERSAL",
]


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InventoryAdjustmentSummaryRowOut(_Base):
    adjustment_type: InventoryAdjustmentSummaryType

    object_id: Annotated[int, Field(ge=1, description="业务对象 ID：盘点单 ID 或事件 ID")]
    object_no: Annotated[str, Field(min_length=1, max_length=128, description="业务对象编号：count_no 或 event_no")]

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    status: Annotated[str, Field(min_length=1, max_length=64, description="当前状态")]

    source_type: str | None = Field(default=None, description="来源类型")
    source_ref: str | None = Field(default=None, description="来源引用号")

    event_type: str | None = Field(default=None, description="事件大类")
    event_kind: str | None = Field(default=None, description="事件动作")
    target_event_id: int | None = Field(default=None, description="被冲回的目标事件 ID")

    occurred_at: datetime | None = Field(default=None, description="业务发生时间")
    committed_at: datetime | None = Field(default=None, description="提交时间")
    created_at: datetime = Field(description="创建时间")

    line_count: Annotated[int, Field(ge=0, description="业务行数")]
    qty_total: int = Field(description="兼容字段：等于 delta_total")

    ledger_row_count: Annotated[int, Field(ge=0, description="台账行数")]
    ledger_reason: str | None = Field(default=None, description="台账原始 reason")
    ledger_reason_canon: str | None = Field(default=None, description="台账稳定口径")
    ledger_sub_reason: str | None = Field(default=None, description="台账具体动作")
    delta_total: int = Field(description="台账净变动")
    abs_delta_total: Annotated[int, Field(ge=0, description="台账绝对变动合计")]
    direction: Annotated[str, Field(min_length=1, max_length=32, description="方向：INCREASE/DECREASE/CONFIRM/PENDING")]

    action_title: Annotated[str, Field(min_length=1, max_length=64, description="后端归纳动作标题")]
    action_summary: Annotated[str, Field(min_length=1, max_length=255, description="后端归纳动作摘要")]

    remark: str | None = Field(default=None, description="备注")
    detail_route: Annotated[str, Field(min_length=1, max_length=255, description="前端详情跳转路由")]


class InventoryAdjustmentSummaryLedgerRowOut(_Base):
    id: Annotated[int, Field(ge=1, description="台账行 ID")]
    event_id: int | None = Field(default=None, description="关联事件 ID")

    ref: str | None = Field(default=None, description="关联单据")
    ref_line: int | None = Field(default=None, description="关联单据行号")
    trace_id: str | None = Field(default=None, description="追溯号")

    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name: str | None = Field(default=None, description="商品名")

    lot_id: int | None = Field(default=None, description="lot_id")
    lot_code: str | None = Field(default=None, description="批次展示码")

    base_item_uom_id: int | None = Field(default=None, description="基础单位 ID")
    base_uom_name: str | None = Field(default=None, description="基础单位名称")

    reason: str = Field(description="台账原始 reason")
    reason_canon: str | None = Field(default=None, description="台账稳定口径")
    sub_reason: str | None = Field(default=None, description="台账具体动作")

    delta: int = Field(description="库存变动")
    after_qty: int = Field(description="变动后数量")

    occurred_at: datetime = Field(description="业务发生时间")
    created_at: datetime = Field(description="台账创建时间")


class InventoryAdjustmentSummaryDetailOut(_Base):
    row: InventoryAdjustmentSummaryRowOut
    ledger_rows: list[InventoryAdjustmentSummaryLedgerRowOut] = Field(default_factory=list)


class InventoryAdjustmentSummaryListOut(_Base):
    items: list[InventoryAdjustmentSummaryRowOut] = Field(default_factory=list)
    total: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1)]
    offset: Annotated[int, Field(ge=0)]


__all__ = [
    "InventoryAdjustmentSummaryType",
    "InventoryAdjustmentSummaryRowOut",
    "InventoryAdjustmentSummaryLedgerRowOut",
    "InventoryAdjustmentSummaryDetailOut",
    "InventoryAdjustmentSummaryListOut",
]
