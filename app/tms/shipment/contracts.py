# app/tms/shipment/contracts.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class ShipmentApplicationError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ConfirmShipmentCommand:
    ref: str
    platform: str
    shop_id: str
    trace_id: str | None

    warehouse_id: int
    shipping_provider_id: int
    scheme_id: int

    tracking_no: str | None
    gross_weight_kg: float | None
    packaging_weight_kg: float | None
    cost_estimated: float | None
    cost_real: float | None
    delivery_time: datetime | None
    status: str | None
    error_code: str | None
    error_message: str | None

    meta: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ConfirmShipmentResult:
    ok: bool
    ref: str
    trace_id: str | None


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

    warehouse_id: int
    shipping_provider_id: int

    carrier_code: str | None
    carrier_name: str | None

    weight_kg: float

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
    tracking_no: str
    shipping_provider_id: int
    carrier_code: str | None
    carrier_name: str | None
    status: str
    label_base64: str | None
    label_format: str | None


@dataclass(frozen=True, slots=True)
class UpdateShipmentStatusCommand:
    record_id: int
    status: str
    delivery_time: datetime | None
    error_code: str | None
    error_message: str | None
    meta: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class UpdateShipmentStatusResult:
    ok: bool
    id: int
    status: str
    delivery_time: datetime | None
