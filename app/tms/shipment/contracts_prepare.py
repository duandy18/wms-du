# app/tms/shipment/contracts_prepare.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ShipPrepareItem(BaseModel):
    item_id: int
    qty: int
    sku: Optional[str] = None
    title: Optional[str] = None
    unit_weight_kg: Optional[float] = None
    line_weight_kg: Optional[float] = None


class ShipPrepareRequest(BaseModel):
    platform: str = Field(..., description="平台，例如 PDD")
    shop_id: str = Field(..., description="店铺 ID，例如 '1'")
    ext_order_no: str = Field(..., description="平台订单号")


class CandidateWarehouseOut(BaseModel):
    """
    候选仓（来自省级路由命中后的集合）
    """

    warehouse_id: int
    warehouse_name: Optional[str] = None
    warehouse_code: Optional[str] = None
    warehouse_active: bool = True
    priority: int = 100


class FulfillmentMissingLineOut(BaseModel):
    item_id: int
    need: int
    available: int


class FulfillmentScanWarehouseOut(BaseModel):
    """
    每个候选仓的整单同仓可履约扫描结果：
    - OK / INSUFFICIENT
    - missing：缺口明细（可解释证据）
    """

    warehouse_id: int
    status: str
    missing: List[FulfillmentMissingLineOut] = Field(default_factory=list)


class ShipPrepareResponse(BaseModel):
    ok: bool = True
    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    ref: str

    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    address_detail: Optional[str] = None

    items: List[ShipPrepareItem] = Field(default_factory=list)
    total_qty: int = 0
    weight_kg: Optional[float] = None
    trace_id: Optional[str] = None

    execution_stage: Optional[str] = None
    ship_committed_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None

    warehouse_id: Optional[int] = None
    warehouse_reason: Optional[str] = None

    candidate_warehouses: List[CandidateWarehouseOut] = Field(default_factory=list)
    fulfillment_scan: List[FulfillmentScanWarehouseOut] = Field(default_factory=list)

    fulfillment_status: Optional[str] = None
    blocked_reasons: List[str] = Field(default_factory=list)
