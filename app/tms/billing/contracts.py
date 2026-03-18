# app/tms/billing/contracts.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReconciliationStatus = Literal["diff", "bill_only", "record_only"]


@dataclass(frozen=True, slots=True)
class ImportCarrierBillCommand:
    carrier_code: str
    import_batch_no: str
    bill_month: str | None
    filename: str
    file_bytes: bytes


@dataclass(frozen=True, slots=True)
class CarrierBillImportRowErrorData:
    row_no: int
    message: str


class CarrierBillImportRowError(BaseModel):
    row_no: int = Field(..., description="Excel 行号（从 1 开始）")
    message: str = Field(..., description="错误原因")


class CarrierBillImportResult(BaseModel):
    ok: bool = True
    carrier_code: str
    import_batch_no: str
    imported_count: int
    skipped_count: int
    error_count: int
    errors: list[CarrierBillImportRowError] = Field(default_factory=list)


class CarrierBillItemOut(BaseModel):
    id: int
    import_batch_no: str
    carrier_code: str
    bill_month: str | None = None

    tracking_no: str
    business_time: datetime | None = None

    destination_province: str | None = None
    destination_city: str | None = None

    billing_weight_kg: float | None = None
    freight_amount: float | None = None
    surcharge_amount: float | None = None
    total_amount: float | None = None

    settlement_object: str | None = None
    order_customer: str | None = None
    sender_name: str | None = None
    network_name: str | None = None
    size_text: str | None = None
    parent_customer: str | None = None

    raw_payload: dict
    created_at: datetime


class CarrierBillItemsResponse(BaseModel):
    ok: bool = True
    rows: list[CarrierBillItemOut]
    total: int


@dataclass(frozen=True, slots=True)
class ReconcileCarrierBillCommand:
    carrier_code: str


class ReconcileCarrierBillIn(BaseModel):
    carrier_code: str = Field(..., description="承运商代码")


class ReconcileCarrierBillResult(BaseModel):
    ok: bool = True
    carrier_code: str

    bill_item_count: int
    diff_count: int
    bill_only_count: int
    record_only_count: int
    updated_count: int

    duplicate_bill_tracking_count: int = 0


class ShippingBillReconciliationRowOut(BaseModel):
    reconciliation_id: int
    status: ReconciliationStatus

    carrier_code: str
    import_batch_no: str
    tracking_no: str

    shipping_record_id: int | None = None
    carrier_bill_item_id: int | None = None

    business_time: datetime | None = None
    destination_province: str | None = None
    destination_city: str | None = None

    billing_weight_kg: float | None = None
    gross_weight_kg: float | None = None
    weight_diff_kg: float | None = None

    freight_amount: float | None = None
    surcharge_amount: float | None = None
    bill_cost_real: float | None = None
    total_amount: float | None = None
    cost_estimated: float | None = None
    cost_diff: float | None = None

    adjust_amount: float | None = None
    created_at: datetime


class ShippingBillReconciliationsResponse(BaseModel):
    ok: bool = True
    rows: list[ShippingBillReconciliationRowOut]
    total: int


class ShippingBillReconciliationOut(BaseModel):
    id: int
    status: ReconciliationStatus

    carrier_code: str
    import_batch_no: str
    tracking_no: str

    shipping_record_id: int | None = None
    carrier_bill_item_id: int | None = None

    weight_diff_kg: float | None = None
    cost_diff: float | None = None
    adjust_amount: float | None = None
    created_at: datetime


class ShippingBillReconciliationShippingRecordOut(BaseModel):
    id: int
    order_ref: str
    platform: str
    shop_id: str

    carrier_code: str | None = None
    carrier_name: str | None = None
    tracking_no: str | None = None

    gross_weight_kg: float | None = None
    cost_estimated: float | None = None

    warehouse_id: int
    shipping_provider_id: int

    dest_province: str | None = None
    dest_city: str | None = None
    created_at: datetime


class ShippingBillReconciliationDetailResponse(BaseModel):
    ok: bool = True
    reconciliation: ShippingBillReconciliationOut
    bill_item: CarrierBillItemOut | None = None
    shipping_record: ShippingBillReconciliationShippingRecordOut | None = None
