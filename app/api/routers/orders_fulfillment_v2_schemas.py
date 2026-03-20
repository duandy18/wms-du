# app/api/routers/orders_fulfillment_v2_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, conint

from app.tms.quote.contracts import QuoteSnapshot


# ---------------------------------------------------------------------------
# 1) 订单拣货 v2
# ---------------------------------------------------------------------------


class PickLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)
    # 终态：按行 batch_code（REQUIRED 必填；NONE 必须为 null；校验在 API 层完成）
    batch_code: Optional[str] = Field(
        default=None,
        description="批次编码：expiry-policy REQUIRED 的商品必填且非空；expiry-policy NONE 的商品必须为 null（合同校验在 API 层完成）",
    )


class PickRequest(BaseModel):
    warehouse_id: conint(gt=0) = Field(..., description="拣货仓库 ID（>0，允许 1）")
    lines: List[PickLineIn] = Field(default_factory=list)
    occurred_at: Optional[datetime] = Field(default=None, description="拣货时间（缺省为当前 UTC 时间）")


class PickResponse(BaseModel):
    item_id: int
    warehouse_id: int
    batch_code: Optional[str]
    picked: int
    stock_after: Optional[int] = None
    ref: str
    status: str


# ---------------------------------------------------------------------------
# 2) ship-with-waybill（模式 2：强制固化“可解释证据包”）
# ---------------------------------------------------------------------------


class ShipWithWaybillMeta(BaseModel):
    quote_snapshot: QuoteSnapshot
    extra: Dict[str, Any] = Field(default_factory=dict)


class ShipWithWaybillRequest(BaseModel):
    warehouse_id: conint(gt=0) = Field(..., description="发货仓库 ID")
    shipping_provider_id: conint(gt=0) = Field(..., description="承运商/网点 ID（强身份，必填）")

    # 冗余展示字段（可选；不参与裁决）
    carrier_code: Optional[str] = Field(None, description="快递公司编码（冗余展示字段）")
    carrier_name: Optional[str] = Field(None, description="快递公司名称（冗余字段）")

    weight_kg: float = Field(..., gt=0, description="包裹毛重（kg）")

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address_detail: Optional[str] = None

    meta: Optional[ShipWithWaybillMeta] = Field(
        default=None,
        description="必须包含 quote_snapshot（input + selected_quote）",
    )


class ShipWithWaybillResponse(BaseModel):
    ok: bool
    ref: str
    tracking_no: str

    shipping_provider_id: int
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None

    status: str = "IN_TRANSIT"
    label_base64: Optional[str] = None
    label_format: Optional[str] = None
