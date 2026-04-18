# app/wms/inbound/contracts/inbound_event_read.py
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


class InboundEventSummaryOut(_Base):
    event_id: Annotated[int, Field(ge=1, description="入库事件 ID")]
    event_no: Annotated[str, Field(min_length=1, max_length=64, description="入库事件单号")]
    event_type: Annotated[str, Field(min_length=1, max_length=16, description="事件大类，当前应为 INBOUND")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    source_type: Annotated[InboundSourceType, Field(description="入库来源类型")]
    source_ref: Annotated[str | None, Field(default=None, max_length=128, description="来源单号/外部引用号")]
    occurred_at: datetime = Field(..., description="业务发生时间")
    committed_at: datetime = Field(..., description="事件提交时间")
    trace_id: Annotated[str, Field(min_length=1, max_length=128, description="技术链路追踪号")]
    event_kind: Annotated[str, Field(min_length=1, max_length=16, description="事件形态，如 COMMIT")]
    status: Annotated[str, Field(min_length=1, max_length=16, description="事件状态，如 COMMITTED")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="整单备注")]


class InboundEventLineOut(_Base):
    line_no: Annotated[int, Field(ge=1, description="事件内行号")]

    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name: Annotated[str | None, Field(default=None, max_length=255, description="商品名称（展示字段）")]
    item_sku: Annotated[str | None, Field(default=None, max_length=64, description="商品 SKU（展示字段）")]

    actual_uom_id: Annotated[int, Field(ge=1, description="实际包装单位 ID")]
    actual_uom_name: Annotated[str | None, Field(default=None, max_length=64, description="实际包装单位名称（展示字段）")]

    barcode_input: Annotated[str | None, Field(default=None, max_length=128, description="条码输入")]
    actual_qty_input: Annotated[int, Field(gt=0, description="实际包装输入数量")]
    actual_ratio_to_base_snapshot: Annotated[int, Field(ge=1, description="提交时冻结的实际换算倍率")]
    qty_base: Annotated[int, Field(gt=0, description="提交时冻结的 base 数量")]

    lot_id: Annotated[int | None, Field(default=None, ge=1, description="实际落账 lot_id")]
    lot_code_input: Annotated[str | None, Field(default=None, max_length=128, description="业务批号/生产批号输入")]
    lot_code: Annotated[str | None, Field(default=None, max_length=128, description="实际 lot_code（展示字段）")]

    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日期")

    po_line_id: Annotated[int | None, Field(default=None, ge=1, description="采购来源时的采购单行 ID")]
    remark: Annotated[str | None, Field(default=None, max_length=255, description="行备注")]


class InboundEventListOut(_Base):
    total: Annotated[int, Field(ge=0, description="总条数")]
    items: list[InboundEventSummaryOut] = Field(default_factory=list, description="事件摘要列表")


class InboundEventDetailOut(_Base):
    event: InboundEventSummaryOut = Field(..., description="事件头摘要")
    lines: list[InboundEventLineOut] = Field(default_factory=list, description="事件明细行")


__all__ = [
    "InboundEventSummaryOut",
    "InboundEventLineOut",
    "InboundEventListOut",
    "InboundEventDetailOut",
]
