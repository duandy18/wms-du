# app/api/routers/outbound_ship_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# -------------------- /ship/calc --------------------


class ShipQuoteOut(BaseModel):
    carrier: str
    name: str
    est_cost: float
    eta: Optional[str] = None
    formula: Optional[str] = None


class ShipCalcRequest(BaseModel):
    weight_kg: float = Field(..., gt=0, description="包裹总重量（kg）")
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    debug_ref: Optional[str] = Field(None, description="调试用标记，不参与计算，仅写入日志/事件")


class ShipCalcResponse(BaseModel):
    ok: bool = True
    weight_kg: float
    dest: Optional[str] = None
    quotes: List[ShipQuoteOut]
    recommended: Optional[str] = None


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

    # 🔹 新增：收件人完整信息
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    address_detail: Optional[str] = None

    items: List[ShipPrepareItem] = Field(default_factory=list)
    total_qty: int = 0

    # 预估总重量（kg）：基于 order_items.qty * items.weight_kg 计算
    weight_kg: Optional[float] = None

    # 订单 trace_id，用于 /ship/confirm -> lifecycle
    trace_id: Optional[str] = None


# -------------------- /ship/confirm --------------------


class ShipConfirmRequest(BaseModel):
    ref: str = Field(..., min_length=1, description="业务引用，如 ORD:PDD:1:EXT123")
    platform: str = Field(..., description="平台，如 PDD")
    shop_id: str = Field(..., description="店铺 ID，如 '1'")
    trace_id: Optional[str] = None

    # 仓库 ID（预留：后续由 Ship Cockpit 或出库链路传入）
    warehouse_id: Optional[int] = Field(None, description="发货仓库 ID（可选）")

    # 承运商信息
    carrier: Optional[str] = Field(None, description="选用的物流公司编码，例如 ZTO / JT / SF")
    carrier_name: Optional[str] = Field(None, description="物流公司名称（冗余字段）")

    # 电子面单 / 运单号
    tracking_no: Optional[str] = Field(None, description="快递运单号 / 电子面单号")

    # 重量信息
    gross_weight_kg: Optional[float] = Field(None, description="实际称重毛重（kg）")
    packaging_weight_kg: Optional[float] = Field(None, description="包材重量（kg）")

    # 费用信息
    cost_estimated: Optional[float] = Field(None, description="系统计算预估费用（元）")
    cost_real: Optional[float] = Field(None, description="月结账单对账后的实际费用（元）")

    # 时效 / 状态
    delivery_time: Optional[datetime] = Field(None, description="实际送达时间（可选）")
    status: Optional[str] = Field(None, description="IN_TRANSIT / DELIVERED / LOST / RETURNED 等")

    # 错误信息（例如面单 API 返回错误）
    error_code: Optional[str] = Field(None, description="错误码")
    error_message: Optional[str] = Field(None, description="错误信息")

    # 额外元数据（会写入审计事件 + shipping_records.meta）
    meta: Optional[Dict[str, Any]] = Field(
        None, description="附加元数据，会写入审计事件 / 发货记录表"
    )


class ShipConfirmResponse(BaseModel):
    ok: bool = True
    ref: str
    trace_id: Optional[str] = None
