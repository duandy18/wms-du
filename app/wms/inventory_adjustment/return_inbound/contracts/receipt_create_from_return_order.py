from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.wms.inventory_adjustment.return_inbound.contracts.receipt_read import InboundReceiptReadOut


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundReceiptCreateFromReturnOrderLineIn(_Base):
    order_line_id: Annotated[int, Field(ge=1, description="订单行 ID")]
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    planned_qty: Annotated[int, Field(ge=1, description="本次退货入库数量（整数）")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="行备注")]


class InboundReceiptCreateFromReturnOrderIn(_Base):
    order_key: Annotated[
        str,
        Field(
            min_length=1,
            max_length=128,
            description="订单键：支持 ORD:PLAT:SHOP:EXT / PLAT:SHOP:EXT / 唯一 ext_order_no",
        ),
    ]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="头备注")]
    lines: Annotated[list[InboundReceiptCreateFromReturnOrderLineIn], Field(min_length=1, description="本次生成行")]


InboundReceiptCreateFromReturnOrderOut = InboundReceiptReadOut
