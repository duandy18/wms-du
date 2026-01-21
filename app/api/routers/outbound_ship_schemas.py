# app/api/routers/outbound_ship_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# -------------------- /ship/calc --------------------


class ShipQuoteOut(BaseModel):
    # ✅ 事实主键与稳定识别码
    provider_id: int
    carrier_code: Optional[str] = None
    carrier_name: str

    # ✅ 方案事实
    scheme_id: int
    scheme_name: str

    # ✅ 报价结果（与 shipping-quote 对齐）
    quote_status: str
    currency: Optional[str] = None
    est_cost: Optional[float] = None

    # ✅ 可解释性（对审计/排障非常关键）
    reasons: List[str] = Field(default_factory=list)
    breakdown: Optional[Dict[str, Any]] = None

    # 预留：时效等
    eta: Optional[str] = None


class ShipCalcRequest(BaseModel):
    # Phase 3：强前置事实（出库侧必须知道从哪个仓发）
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
    currency: Optional[str] = None


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


# -------------------- /ship/confirm --------------------


class ShipConfirmRequest(BaseModel):
    ref: str = Field(..., min_length=1, description="业务引用，如 ORD:PDD:1:EXT123")
    platform: str = Field(..., description="平台，如 PDD")
    shop_id: str = Field(..., description="店铺 ID，如 '1'")
    trace_id: Optional[str] = None

    warehouse_id: Optional[int] = Field(None, description="发货仓库 ID（Phase 3 建议必填）")

    carrier: Optional[str] = Field(None, description="选用的物流公司编码，例如 ZTO / JT / SF")
    carrier_name: Optional[str] = Field(None, description="物流公司名称（冗余字段）")

    # ✅ Phase 3：方案事实（用于可追责的出库确认）
    scheme_id: Optional[int] = Field(None, description="选用的运价方案 ID（Phase 3 建议必填）")

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
