# app/shipping_assist/shipment/contracts.py
from __future__ import annotations

from dataclasses import dataclass


class ShipmentApplicationError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ShipCommitAuditCommand:
    ref: str
    platform: str
    shop_id: str
    trace_id: str | None
    meta: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ShipCommitAuditResult:
    ok: bool
    ref: str
    trace_id: str | None


@dataclass(frozen=True, slots=True)
class ShipWithWaybillCommand:
    order_ref: str
    trace_id: str | None

    platform: str
    shop_id: str
    ext_order_no: str
    package_no: int

    receiver_name: str | None
    receiver_phone: str | None
    province: str | None
    city: str | None
    district: str | None
    address_detail: str | None

    meta: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ShipWithWaybillResult:
    ok: bool
    ref: str
    package_no: int
    tracking_no: str

    shipping_provider_id: int
    shipping_provider_code: str | None
    shipping_provider_name: str | None

    status: str

    # ✅ 替换掉 label_base64
    print_data: dict | None
    template_url: str | None
