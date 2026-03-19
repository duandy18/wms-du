# app/tms/billing/contracts.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReconciliationStatus = Literal["diff", "bill_only"]
ApprovedReasonCode = Literal["matched", "approved_bill_only", "resolved"]
ReconciliationHistoryResultStatus = Literal["matched", "approved_bill_only", "resolved"]


@dataclass(frozen=True, slots=True)
class ImportCarrierBillCommand:
    carrier_code: str
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
    imported_count: int
    skipped_count: int
    error_count: int
    errors: list[CarrierBillImportRowError] = Field(default_factory=list)


class CarrierBillItemOut(BaseModel):
    id: int
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
    matched_count: int
    bill_only_count: int
    diff_count: int
    updated_count: int

    duplicate_bill_tracking_count: int = 0


class ShippingBillReconciliationRowOut(BaseModel):
    reconciliation_id: int
    status: ReconciliationStatus

    carrier_code: str
    tracking_no: str

    shipping_record_id: int | None = None
    carrier_bill_item_id: int

    weight_diff_kg: float | None = None
    cost_diff: float | None = None
    adjust_amount: float | None = None
    approved_reason_code: ApprovedReasonCode | None = None
    approved_reason_text: str | None = None
    approved_at: datetime | None = None
    created_at: datetime


class ShippingBillReconciliationsResponse(BaseModel):
    ok: bool = True
    rows: list[ShippingBillReconciliationRowOut]
    total: int


class ApproveShippingBillReconciliationIn(BaseModel):
    approved_reason_code: Literal["approved_bill_only", "resolved"] = Field(
        ...,
        description="最终确认结果 code：bill_only 只能写 approved_bill_only，diff 只能写 resolved",
    )
    adjust_amount: float | None = Field(
        default=None,
        description="调整金额；为空时按 0 处理",
    )
    approved_reason_text: str | None = Field(
        default=None,
        description="备注说明；一般可不填，作为补充说明",
    )


class ApproveShippingBillReconciliationOut(BaseModel):
    ok: bool = True
    reconciliation_id: int
    history_result_status: ReconciliationHistoryResultStatus


class ShippingBillReconciliationHistoryRowOut(BaseModel):
    id: int
    carrier_bill_item_id: int
    shipping_record_id: int | None = None

    carrier_code: str
    tracking_no: str

    result_status: ReconciliationHistoryResultStatus
    approved_reason_code: ApprovedReasonCode

    weight_diff_kg: float | None = None
    cost_diff: float | None = None
    adjust_amount: float | None = None
    approved_reason_text: str | None = None
    archived_at: datetime


class ShippingBillReconciliationHistoriesResponse(BaseModel):
    ok: bool = True
    rows: list[ShippingBillReconciliationHistoryRowOut]
    total: int


class BillingCostAnalysisSummaryOut(BaseModel):
    ticket_count: int
    total_cost: float


class BillingCostAnalysisByCarrierRowOut(BaseModel):
    carrier_code: str | None = None
    ticket_count: int
    total_cost: float


class BillingCostAnalysisByTimeRowOut(BaseModel):
    bucket: str
    ticket_count: int
    total_cost: float


class BillingCostAnalysisResponse(BaseModel):
    ok: bool = True
    summary: BillingCostAnalysisSummaryOut
    by_carrier: list[BillingCostAnalysisByCarrierRowOut]
    by_time: list[BillingCostAnalysisByTimeRowOut]
