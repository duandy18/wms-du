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


class InboundReceiptCreateFromPurchaseIn(_Base):
    source_doc_id: Annotated[int, Field(ge=1, description="采购单 ID")]
    warehouse_id: Annotated[int, Field(ge=1, description="仓库 ID")]
    remark: Annotated[str | None, Field(default=None, max_length=500, description="头备注")]


InboundReceiptCreateFromPurchaseOut = InboundReceiptReadOut


__all__ = [
    "InboundReceiptCreateFromPurchaseIn",
    "InboundReceiptCreateFromPurchaseOut",
]
