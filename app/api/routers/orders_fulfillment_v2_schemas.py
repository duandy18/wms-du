# app/api/routers/orders_fulfillment_v2_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, conint, constr


# ---------------------------------------------------------------------------
# 1) 订单预占 v2
# ---------------------------------------------------------------------------


class ReserveLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)


class ReserveRequest(BaseModel):
    lines: List[ReserveLineIn] = Field(default_factory=list)


class ReserveResponse(BaseModel):
    status: str
    ref: str
    reservation_id: Optional[int] = None
    lines: int


# ---------------------------------------------------------------------------
# 2) 订单拣货 v2
# ---------------------------------------------------------------------------


class PickLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)


class PickRequest(BaseModel):
    warehouse_id: conint(gt=0) = Field(..., description="拣货仓库 ID（>0，允许 1）")
    batch_code: constr(min_length=1)
    lines: List[PickLineIn] = Field(default_factory=list)
    occurred_at: Optional[datetime] = Field(
        default=None, description="拣货时间（缺省为当前 UTC 时间）"
    )


class PickResponse(BaseModel):
    item_id: int
    warehouse_id: int
    batch_code: str
    picked: int
    stock_after: Optional[int] = None
    ref: str
    status: str


# ---------------------------------------------------------------------------
# 3) 订单发运 v2（只写审计）
# ---------------------------------------------------------------------------


class ShipLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)


class ShipRequest(BaseModel):
    warehouse_id: conint(gt=0)
    lines: List[ShipLineIn] = Field(default_factory=list)
    occurred_at: Optional[datetime] = Field(
        default=None, description="发运时间（缺省为当前 UTC 时间）"
    )


class ShipResponse(BaseModel):
    status: str
    ref: str
    event: str = "SHIP_COMMIT"


# ---------------------------------------------------------------------------
# 4) ship-with-waybill（模式 2：强制固化“可解释证据包”）
# ---------------------------------------------------------------------------


class ShipWithWaybillRequest(BaseModel):
    warehouse_id: conint(gt=0) = Field(..., description="发货仓库 ID")
    carrier_code: constr(min_length=1) = Field(..., description="快递公司编码，例如 ZTO / JT / SF")
    carrier_name: Optional[str] = Field(None, description="快递公司名称（冗余字段）")
    weight_kg: float = Field(..., gt=0, description="包裹毛重（kg）")

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address_detail: Optional[str] = None

    # ✅ 新标准：必须包含 quote_snapshot（input + selected_quote），并且 selected_quote.reasons 非空
    meta: Optional[Dict[str, Any]] = Field(
        default=None, description="必须包含 quote_snapshot（input + selected_quote）"
    )


class ShipWithWaybillResponse(BaseModel):
    ok: bool
    ref: str
    tracking_no: str
    carrier_code: str
    carrier_name: Optional[str] = None
    status: str = "IN_TRANSIT"
    label_base64: Optional[str] = None
    label_format: Optional[str] = None
