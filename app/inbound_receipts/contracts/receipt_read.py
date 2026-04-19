from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.inbound_receipts.contracts.enums import (
    InboundReceiptSourceType,
    InboundReceiptStatus,
)


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundReceiptLineReadOut(_Base):
    id: Annotated[int, Field(ge=1, description="任务行 ID")]
    line_no: Annotated[int, Field(ge=1, description="任务行号")]
    source_line_id: Annotated[int | None, Field(default=None, ge=1, description="来源行 ID")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_uom_id: Annotated[int, Field(ge=1, description="包装单位 ID")]
    planned_qty: Annotated[int, Field(ge=1, description="任务数量（整数）")]
    item_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="商品名快照")]
    item_spec_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="规格快照")]
    uom_name_snapshot: Annotated[str | None, Field(default=None, max_length=64, description="单位名快照")]
    ratio_to_base_snapshot: Annotated[int, Field(ge=1, description="倍率快照（整数）")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="行备注")]


class InboundReceiptReadOut(_Base):
    id: Annotated[int, Field(ge=1, description="任务单 ID")]
    receipt_no: Annotated[str, Field(min_length=1, max_length=64, description="入库任务号")]
    source_type: InboundReceiptSourceType
    source_doc_id: Annotated[int | None, Field(default=None, ge=1, description="来源单 ID")]
    source_doc_no_snapshot: Annotated[str | None, Field(default=None, max_length=128, description="来源单号快照")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    warehouse_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="仓库名快照")]
    supplier_id: Annotated[int | None, Field(default=None, ge=1, description="供应商 ID")]
    counterparty_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="对方名称快照")]
    status: InboundReceiptStatus
    remark: Annotated[str | None, Field(default=None, max_length=500, description="头备注")]
    created_by: Annotated[int | None, Field(default=None, ge=1, description="创建人 ID")]
    released_at: datetime | None = Field(default=None, description="发布时间")
    lines: list[InboundReceiptLineReadOut] = Field(default_factory=list, description="任务行")


class InboundReceiptListItemOut(_Base):
    id: Annotated[int, Field(ge=1, description="任务单 ID")]
    receipt_no: Annotated[str, Field(min_length=1, max_length=64, description="入库任务号")]
    source_type: InboundReceiptSourceType
    source_doc_no_snapshot: Annotated[str | None, Field(default=None, max_length=128, description="来源单号快照")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    warehouse_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="仓库名快照")]
    supplier_id: Annotated[int | None, Field(default=None, ge=1, description="供应商 ID")]
    counterparty_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="对方名称快照")]
    status: InboundReceiptStatus
    remark: Annotated[str | None, Field(default=None, max_length=500, description="头备注")]
    released_at: datetime | None = Field(default=None, description="发布时间")


class InboundReceiptListOut(_Base):
    items: list[InboundReceiptListItemOut] = Field(default_factory=list, description="列表项")
    total: Annotated[int, Field(ge=0, description="总数")]


class InboundReceiptProgressLineOut(_Base):
    line_no: Annotated[int, Field(ge=1, description="任务行号")]
    planned_qty: Annotated[int, Field(ge=0, description="任务数量（整数）")]
    received_qty: Annotated[Decimal, Field(ge=0, description="累计已收（按计划包装折算，可能为小数）")]
    remaining_qty: Annotated[Decimal, Field(ge=0, description="剩余待收（按计划包装折算，可能为小数）")]


class InboundReceiptProgressOut(_Base):
    receipt_id: Annotated[int, Field(ge=1, description="任务单 ID")]
    receipt_no: Annotated[str, Field(min_length=1, max_length=64, description="入库任务号")]
    lines: list[InboundReceiptProgressLineOut] = Field(default_factory=list, description="进度行")


__all__ = [
    "InboundReceiptLineReadOut",
    "InboundReceiptReadOut",
    "InboundReceiptListItemOut",
    "InboundReceiptListOut",
    "InboundReceiptProgressLineOut",
    "InboundReceiptProgressOut",
]
