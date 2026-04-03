# app/tms/shipment/api_contracts.py
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, conint


class ShipWithWaybillMeta(BaseModel):
    extra: Dict[str, Any] = Field(default_factory=dict)


class ShipWithWaybillRequest(BaseModel):
    package_no: conint(gt=0) = Field(..., description="包裹序号，从 1 开始")

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    address_detail: Optional[str] = None

    meta: Optional[ShipWithWaybillMeta] = None


class ShipWithWaybillResponse(BaseModel):
    ok: bool
    ref: str
    package_no: int
    tracking_no: str

    shipping_provider_id: int
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None

    status: str = "IN_TRANSIT"

    # ✅ 新结构
    print_data: Optional[Dict[str, Any]] = None
    template_url: Optional[str] = None
