# app/schemas/purchase_order_receive_workbench.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PoSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    po_id: int
    warehouse_id: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    status: Optional[str] = None
    occurred_at: Optional[datetime] = None


class ReceiptSummaryOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    receipt_id: int
    ref: str
    status: str
    occurred_at: datetime


class WorkbenchBatchRowOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    batch_code: str
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None
    qty_received: int


class WorkbenchRowOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    po_line_id: int
    line_no: int
    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None

    ordered_qty: int = Field(..., description="计划数量（base 口径）")
    confirmed_received_qty: int = Field(..., description="已确认实收（base，来自 CONFIRMED receipts 聚合）")
    draft_received_qty: int = Field(..., description="草稿录入实收（base，来自当前 DRAFT receipt 聚合）")
    remaining_qty: int = Field(..., description="剩余应收（base）")

    # draft 批次聚合
    batches: List[WorkbenchBatchRowOut] = Field(default_factory=list)

    # confirmed 批次聚合
    confirmed_batches: List[WorkbenchBatchRowOut] = Field(default_factory=list)

    # ✅ 新增：合并批次聚合（confirmed + draft）
    all_batches: List[WorkbenchBatchRowOut] = Field(default_factory=list)


class WorkbenchExplainOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    confirmable: bool
    blocking_errors: List[dict] = Field(default_factory=list)
    normalized_lines_preview: List[dict] = Field(default_factory=list)


class WorkbenchCapsOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    can_confirm: bool
    can_start_draft: bool
    receipt_id: Optional[int] = None


class PurchaseOrderReceiveWorkbenchOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    po_summary: PoSummaryOut
    receipt: Optional[ReceiptSummaryOut] = None
    rows: List[WorkbenchRowOut]
    explain: Optional[WorkbenchExplainOut] = None
    caps: WorkbenchCapsOut
