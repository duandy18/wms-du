# app/tms/billing/contracts.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, Field


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
    import_batch_no: str


class ReconcileCarrierBillIn(BaseModel):
    carrier_code: str = Field(..., description="承运商代码")
    import_batch_no: str = Field(..., description="账单导入批次号")


class ReconcileCarrierBillResult(BaseModel):
    ok: bool = True
    carrier_code: str
    import_batch_no: str

    bill_item_count: int
    matched_count: int
    diff_count: int
    unmatched_count: int
    updated_count: int

    duplicate_bill_tracking_count: int = 0
