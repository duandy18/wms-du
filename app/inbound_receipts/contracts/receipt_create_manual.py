from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.inbound_receipts.contracts.receipt_read import InboundReceiptReadOut


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class InboundReceiptCreateManualLineIn(_Base):
    item_id: Annotated[int, Field(ge=1, description="商品 ID")]
    item_uom_id: Annotated[int, Field(ge=1, description="包装单位 ID")]
    planned_qty: Annotated[int, Field(ge=1, description="任务数量（整数）")]
    item_name_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="商品名（前端展示传入，可空）")]
    item_spec_snapshot: Annotated[str | None, Field(default=None, max_length=255, description="规格（前端展示传入，可空）")]
    uom_name_snapshot: Annotated[str | None, Field(default=None, max_length=64, description="单位名（前端展示传入，可空）")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="行备注")]


class InboundReceiptCreateManualIn(_Base):
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    supplier_id: Annotated[int | None, Field(default=None, ge=1, description="供应商 ID")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="头备注")]
    lines: Annotated[list[InboundReceiptCreateManualLineIn], Field(min_length=1, description="手动入库任务行")]


InboundReceiptCreateManualOut = InboundReceiptReadOut


__all__ = [
    "InboundReceiptCreateManualLineIn",
    "InboundReceiptCreateManualIn",
    "InboundReceiptCreateManualOut",
]
