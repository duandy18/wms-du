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
    """
    入库事件列表 / 详情共用的事件头摘要。

    说明：
    - 直接对应 wms_events 的稳定读面
    - event_id 是业务事件锚点
    - trace_id 是技术链路锚点
    - 不把 receipt 语义重新混进来
    """

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
    """
    入库事件详情中的明细行。

    说明：
    - 直接对应 inbound_event_lines 的稳定读面
    - qty_base / ratio_to_base_snapshot 为交易快照
    - item_name / item_sku / uom_name / lot_code 为展示字段，可由 service 拼装
    """

    line_no: Annotated[int, Field(ge=1, description="事件内行号")]

    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name: Annotated[str | None, Field(default=None, max_length=255, description="商品名称（展示字段）")]
    item_sku: Annotated[str | None, Field(default=None, max_length=64, description="商品 SKU（展示字段）")]

    uom_id: Annotated[int, Field(ge=1, description="包装单位 ID")]
    uom_name: Annotated[str | None, Field(default=None, max_length=64, description="包装单位名称（展示字段）")]

    barcode_input: Annotated[str | None, Field(default=None, max_length=128, description="条码输入")]
    qty_input: Annotated[int, Field(gt=0, description="输入数量")]
    ratio_to_base_snapshot: Annotated[int, Field(ge=1, description="提交时冻结的换算倍率")]
    qty_base: Annotated[int, Field(gt=0, description="提交时冻结的 base 数量")]

    lot_id: Annotated[int | None, Field(default=None, ge=1, description="实际落账 lot_id")]
    lot_code_input: Annotated[str | None, Field(default=None, max_length=128, description="业务批号/生产批号输入")]
    lot_code: Annotated[str | None, Field(default=None, max_length=128, description="实际 lot_code（展示字段）")]

    production_date: date | None = Field(default=None, description="生产日期")
    expiry_date: date | None = Field(default=None, description="到期日期")

    po_line_id: Annotated[int | None, Field(default=None, ge=1, description="采购来源时的采购单行 ID")]
    remark: Annotated[str | None, Field(default=None, max_length=255, description="行备注")]


class InboundEventListOut(_Base):
    """
    入库事件列表返回。
    """

    total: Annotated[int, Field(ge=0, description="总条数")]
    items: list[InboundEventSummaryOut] = Field(default_factory=list, description="事件摘要列表")


class InboundEventDetailOut(_Base):
    """
    入库事件详情返回。
    """

    event: InboundEventSummaryOut = Field(..., description="事件头摘要")
    lines: list[InboundEventLineOut] = Field(default_factory=list, description="事件明细行")


__all__ = [
    "InboundEventSummaryOut",
    "InboundEventLineOut",
    "InboundEventListOut",
    "InboundEventDetailOut",
]
