from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.wms.inventory_adjustment.return_inbound.contracts.enums import (
    InboundReceiptSourceType,
    InboundReceiptStatus,
)
from app.pms.public.items.contracts.item_policy import (
    ExpiryPolicy,
    LotSourcePolicy,
    ShelfLifeUnit,
)


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundTaskListItemOut(_Base):
    receipt_id: Annotated[int, Field(ge=1, description="任务单 ID")]
    receipt_no: Annotated[str, Field(min_length=1, max_length=64, description="入库任务号")]
    source_type: InboundReceiptSourceType
    source_doc_no_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=128, description="来源单号快照"),
    ]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    warehouse_name_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=255, description="仓库名快照"),
    ]
    supplier_id: Annotated[int | None, Field(default=None, ge=1, description="供应商 ID")]
    counterparty_name_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=255, description="对方名称快照"),
    ]
    status: InboundReceiptStatus
    released_at: datetime | None = Field(default=None, description="发布时间")
    last_operated_at: datetime | None = Field(default=None, description="最近收货时间")
    line_count: Annotated[int, Field(ge=0, description="任务行数")]
    total_planned_qty: Annotated[int, Field(ge=0, description="总任务数量（按计划包装，整数）")]
    total_received_qty: Annotated[Decimal, Field(ge=0, description="累计已收总数（按计划包装折算）")]
    total_remaining_qty: Annotated[Decimal, Field(ge=0, description="总剩余待收（按计划包装折算）")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="头备注")]


class InboundTaskListOut(_Base):
    items: list[InboundTaskListItemOut] = Field(default_factory=list, description="WMS 入库任务列表")
    total: Annotated[int, Field(ge=0, description="总数")]


class InboundTaskLineOut(_Base):
    line_no: Annotated[int, Field(ge=1, description="任务行号")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_uom_id: Annotated[int, Field(ge=1, description="计划包装单位 ID")]
    planned_qty: Annotated[int, Field(ge=0, description="计划包装数量（整数）")]
    planned_qty_base: Annotated[int, Field(ge=0, description="计划基础数量（整数）")]
    item_name_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=255, description="商品名快照"),
    ]
    item_spec_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=255, description="规格快照"),
    ]
    uom_name_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=64, description="计划单位名快照"),
    ]
    ratio_to_base_snapshot: Annotated[int, Field(ge=1, description="计划倍率快照（整数）")]

    expiry_policy: ExpiryPolicy = Field(description="有效期策略")
    lot_source_policy: LotSourcePolicy = Field(description="批次来源策略")
    derivation_allowed: bool = Field(description="是否允许按保质期推导日期")
    shelf_life_value: Annotated[
        int | None,
        Field(default=None, gt=0, description="保质期数值"),
    ]
    shelf_life_unit: ShelfLifeUnit | None = Field(default=None, description="保质期单位")

    received_qty: Annotated[Decimal, Field(ge=0, description="累计已收（按计划包装折算，可能为小数）")]
    remaining_qty: Annotated[Decimal, Field(ge=0, description="剩余待收（按计划包装折算，可能为小数）")]

    received_qty_base: Annotated[int, Field(ge=0, description="累计已收基础数量（整数）")]
    remaining_qty_base: Annotated[int, Field(ge=0, description="剩余待收基础数量（整数）")]

    remark: Annotated[str | None, Field(default=None, max_length=500, description="行备注")]


class InboundTaskReadOut(_Base):
    receipt_id: Annotated[int, Field(ge=1, description="任务单 ID")]
    receipt_no: Annotated[str, Field(min_length=1, max_length=64, description="入库任务号")]
    source_type: InboundReceiptSourceType
    source_doc_no_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=128, description="来源单号快照"),
    ]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    warehouse_name_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=255, description="仓库名快照"),
    ]
    supplier_id: Annotated[int | None, Field(default=None, ge=1, description="供应商 ID")]
    counterparty_name_snapshot: Annotated[
        str | None,
        Field(default=None, max_length=255, description="对方名称快照"),
    ]
    status: InboundReceiptStatus
    remark: Annotated[str | None, Field(default=None, max_length=500, description="头备注")]
    lines: list[InboundTaskLineOut] = Field(default_factory=list, description="任务行")


__all__ = [
    "InboundTaskListItemOut",
    "InboundTaskListOut",
    "InboundTaskLineOut",
    "InboundTaskReadOut",
]
