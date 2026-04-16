# app/procurement/contracts/purchase_order_source_options.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


PurchaseOrderSourceCompletionStatus = Literal[
    "NOT_RECEIVED",
    "PARTIAL",
    "RECEIVED",
]


class PurchaseOrderSourceOptionOut(BaseModel):
    """
    采购来源下拉项（给 WMS 入库页来源区使用）。

    设计原则：
    - procurement 负责提供“可选采购来源”的窄读面
    - WMS 前端只消费这份合同，不自行聚合 /purchase-orders/completion
    - 一条 option = 一张采购单，而不是采购单行
    """

    po_id: int = Field(..., gt=0)
    po_no: str = Field(..., min_length=1, max_length=64)

    warehouse_id: int = Field(..., gt=0)

    supplier_id: int = Field(..., gt=0)
    supplier_name: str = Field(..., min_length=1, max_length=255)

    purchase_time: datetime = Field(...)

    po_status: str = Field(..., min_length=1, max_length=32)
    completion_status: PurchaseOrderSourceCompletionStatus = Field(...)
    last_received_at: datetime | None = Field(default=None)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PurchaseOrderSourceOptionsOut(BaseModel):
    """
    采购来源下拉列表返回。
    """

    items: list[PurchaseOrderSourceOptionOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, extra="forbid")


__all__ = [
    "PurchaseOrderSourceCompletionStatus",
    "PurchaseOrderSourceOptionOut",
    "PurchaseOrderSourceOptionsOut",
]
