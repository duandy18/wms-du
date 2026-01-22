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

    # ✅ 不预设、不兜底：不直接给 warehouse_id
    warehouse_id: Optional[int] = None
    warehouse_reason: Optional[str] = None

    # ✅ 主线：省级路由命中的候选仓集合（可能 0/1/N）
    candidate_warehouses: List[CandidateWarehouseOut] = Field(default_factory=list)

    # ✅ 扫描报告：每个候选仓的 OK/缺口
    fulfillment_scan: List[FulfillmentScanWarehouseOut] = Field(default_factory=list)

    # ✅ 不可履约事实（用于“智能退货/取消”）
    fulfillment_status: Optional[str] = None  # OK / FULFILLMENT_BLOCKED
    blocked_reasons: List[str] = Field(default_factory=list)
    blocked_detail: Optional[Dict[str, Any]] = None


# -------------------- /ship/confirm --------------------


class ShipConfirmRequest(BaseModel):
    ref: str = Field(..., min_length=1, description="业务引用，如 ORD:PDD:1:EXT123")
    platform: str = Field(..., description="平台，如 PDD")
    shop_id: str = Field(..., description="店铺 ID，如 '1'")
    trace_id: Optional[str] = None

    warehouse_id: Optional[int] = Field(None, description="发货仓库 ID（建议必填）")

    carrier: Optional[str] = Field(None, description="选用的物流公司编码，例如 ZTO / JT / SF")
    carrier_name: Optional[str] = Field(None, description="物流公司名称（冗余字段）")

    scheme_id: Optional[int] = Field(None, description="选用的运价方案 ID（建议必填）")

    tracking_no: Optional[str] = Field(None, description="快递运单号 / 电子面单号")

    gross_weight_kg: Optional[float] = Field(None, description="实际称重毛重（kg）")
    packaging_weight_kg: Optional[float] = Field(None, description="包材重量（kg）")

    cost_estimated: Optional[float] = Field(None, description="系统计算预估费用（元）")
    cost_real: Optional[float] = Field(None, description="月结账单对账后的实际费用（元）")

    delivery_time: Optional[datetime] = Field(None, description="实际送达时间（可选）")
    status: Optional[str] = Field(None, description="IN_TRANSIT / DELIVERED / LOST / RETURNED 等")

    error_code: Optional[str] = Field(None, description="错误码")
    error_message: Optional[str] = Field(None, description="错误信息")

    meta: Optional[Dict[str, Any]] = Field(None, description="附加元数据，会写入审计事件 / 发货记录表")


class ShipConfirmResponse(BaseModel):
    ok: bool = True
    ref: str
    trace_id: Optional[str] = None
