# app/api/routers/devconsole_orders_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DevOrderInfo(BaseModel):
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    status: Optional[str] = None
    trace_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    warehouse_id: Optional[int] = None
    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None


class DevOrderView(BaseModel):
    order: DevOrderInfo
    trace_id: Optional[str] = Field(
        None,
        description="订单关联 trace_id，可直接跳转生命周期/trace 页面",
    )


class DevOrderItemFact(BaseModel):
    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None
    qty_ordered: int
    qty_shipped: int
    qty_returned: int
    qty_remaining_refundable: int


class DevOrderFacts(BaseModel):
    order: DevOrderInfo
    items: List[DevOrderItemFact] = Field(default_factory=list)


class DevOrderSummary(BaseModel):
    id: int
    platform: str
    shop_id: str
    ext_order_no: str
    status: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    warehouse_id: Optional[int] = None
    order_amount: Optional[float] = None
    pay_amount: Optional[float] = None


class DevOrderReconcileLine(BaseModel):
    item_id: int
    sku_id: Optional[str] = None
    title: Optional[str] = None
    qty_ordered: int
    qty_shipped: int
    qty_returned: int
    remaining_refundable: int


class DevOrderReconcileResultModel(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    issues: List[str] = Field(default_factory=list)
    lines: List[DevOrderReconcileLine] = Field(default_factory=list)


class DevReconcileRangeResult(BaseModel):
    count: int
    order_ids: List[int] = Field(default_factory=list)


class DevDemoOrderOut(BaseModel):
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    trace_id: Optional[str] = None


class DevEnsureWarehouseOut(BaseModel):
    ok: bool
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    store_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    source: str
    message: Optional[str] = None
