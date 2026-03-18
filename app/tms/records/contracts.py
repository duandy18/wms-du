# app/tms/records/contracts.py
#
# 分拆说明：
# - 本文件承载 TMS / Records（物流台帐）只读合同；
# - shipping_records 的来源是发货执行流程写入的运输事实；
# - Records 域仅提供台帐列表与导出，不提供详情写入、不提供状态维护。
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ShippingLedgerRow(BaseModel):
    id: int
    order_ref: str

    warehouse_id: int | None = Field(default=None)
    shipping_provider_id: int | None = Field(default=None)

    carrier_code: str | None = None
    carrier_name: str | None = None
    tracking_no: str | None = None

    freight_estimated: float | None = None
    surcharge_estimated: float | None = None
    cost_estimated: float | None = None

    gross_weight_kg: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None

    sender: str | None = None

    dest_province: str | None = None
    dest_city: str | None = None

    created_at: datetime


class ShippingLedgerListResponse(BaseModel):
    ok: bool = True
    rows: list[ShippingLedgerRow]
    total: int


class RecordsCostAnalysisSummaryOut(BaseModel):
    ticket_count: int
    total_cost: float


class RecordsCostAnalysisByCarrierRowOut(BaseModel):
    carrier_code: str | None = None
    ticket_count: int
    total_cost: float


class RecordsCostAnalysisByTimeRowOut(BaseModel):
    bucket: str
    ticket_count: int
    total_cost: float


class RecordsCostAnalysisResponse(BaseModel):
    ok: bool = True
    summary: RecordsCostAnalysisSummaryOut
    by_carrier: list[RecordsCostAnalysisByCarrierRowOut]
    by_time: list[RecordsCostAnalysisByTimeRowOut]
