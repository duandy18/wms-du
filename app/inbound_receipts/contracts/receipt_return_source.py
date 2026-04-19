from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.inbound_receipts.contracts.enums import InboundReceiptStatus


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundReceiptReturnSourceLineOut(_Base):
    order_line_id: Annotated[int, Field(ge=1, description="订单行 ID")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="商品名快照")]
    item_spec_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="规格快照")]
    item_uom_id: Annotated[int, Field(ge=1, description="建议入库包装单位 ID")]
    uom_name_snapshot: Annotated[str | None, Field(default=None, max_length=64, description="建议入库单位名")]
    ratio_to_base_snapshot: Annotated[int, Field(ge=1, description="建议入库倍率快照（整数）")]
    qty_ordered: Annotated[int, Field(ge=0, description="下单数量（整数）")]
    qty_shipped: Annotated[int, Field(ge=0, description="已发数量（整数）")]
    qty_returned: Annotated[int, Field(ge=0, description="已退数量（整数）")]
    qty_remaining_refundable: Annotated[int, Field(ge=0, description="剩余可退数量（整数）")]
    suggested_planned_qty: Annotated[int, Field(ge=0, description="建议本次生成数量（整数）")]


class InboundReceiptReturnSourceOut(_Base):
    order_id: Annotated[int, Field(ge=1, description="OMS 订单 ID")]
    order_ref: Annotated[str, Field(min_length=1, max_length=128, description="规范订单键")]
    platform: Annotated[str | None, Field(default=None, max_length=32, description="平台")]
    shop_id: Annotated[str | None, Field(default=None, max_length=64, description="店铺 ID")]
    ext_order_no: Annotated[str | None, Field(default=None, max_length=128, description="原订单号")]
    warehouse_id: Annotated[int, Field(ge=1, description="退货入库仓库 ID")]
    warehouse_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="仓库名快照")]
    remaining_qty: Annotated[int, Field(ge=0, description="整单剩余可退数量（整数）")]
    existing_receipt_id: Annotated[int | None, Field(default=None, ge=1, description="已存在退货入库单 ID")]
    existing_receipt_no: Annotated[str | None, Field(default=None, max_length=64, description="已存在退货入库单号")]
    existing_receipt_status: InboundReceiptStatus | None = Field(default=None, description="已存在退货入库单状态")
    lines: list[InboundReceiptReturnSourceLineOut] = Field(default_factory=list, description="退货来源行")
