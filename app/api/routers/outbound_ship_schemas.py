# app/api/routers/outbound_ship_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# -------------------- /ship/calc --------------------


class ShipQuoteOut(BaseModel):
    provider_id: int
    carrier_code: Optional[str] = None
    carrier_name: str

    scheme_id: int
    scheme_name: str

    quote_status: str
    currency: Optional[str] = None
    est_cost: Optional[float] = None

    reasons: List[str] = Field(default_factory=list)
    breakdown: Optional[Dict[str, Any]] = None

    eta: Optional[str] = None


class ShipCalcRequest(BaseModel):
    warehouse_id: int = Field(..., ge=1, description="发货仓库 ID（Phase 3 强前置事实）")

    weight_kg: float = Field(..., gt=0, description="包裹总重量（kg）")
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    debug_ref: Optional[str] = Field(None, description="调试用标记，不参与计算，仅写入日志/事件")


class ShipRecommendedOut(BaseModel):
    provider_id: int
    carrier_code: Optional[str] = None
    scheme_id: int
    est_cost: Optional[float] = None
    currency: Optional[float] = None


class ShipCalcResponse(BaseModel):
    ok: bool = True
    weight_kg: float
    dest: Optional[str] = None
    quotes: List[ShipQuoteOut]
    recommended: Optional[ShipRecommendedOut] = None


# -------------------- /ship/prepare-from-order --------------------


class ShipPrepareItem(BaseModel):
    item_id: int
    qty: int


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

    # ✅ 执行域展示字段（路 A：阶段真相 + 出库事实）
    execution_stage: Optional[str] = None
    ship_committed_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None

    # ✅ 不预设、不兜底：不直接给 warehouse_id
    warehouse_id: Optional[int] = None
    warehouse_reason: Optional[str] = None

    # ✅ 主线：省级路由命中的候选仓集合（可能 0/1/N）
    candidate_warehouses: List[CandidateWarehouseOut] = Field(default_factory=list)

    # ✅ 扫描报告：每个候选仓的 OK/缺口
    fulfillment_scan: List[FulfillmentScanWarehouseOut] = Field(default_factory=list)

    # ✅ 路由/阻断字段（非阶段）：OK / FULFILLMENT_BLOCKED
    fulfillment_status: Optional[str] = None
    blocked_reasons: List[str] = Field(default_factory=list)
