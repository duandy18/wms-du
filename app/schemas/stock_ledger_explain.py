# app/schemas/stock_ledger_explain.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ExplainAnchor(BaseModel):
    ref: str
    trace_id: Optional[str] = None


class ExplainReceipt(BaseModel):
    id: int
    warehouse_id: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    source_type: str
    source_id: Optional[int] = None
    receive_task_id: Optional[int] = None
    ref: str
    trace_id: Optional[str] = None
    status: str
    remark: Optional[str] = None
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExplainReceiptLine(BaseModel):
    id: int
    receipt_id: int
    line_no: int
    po_line_id: Optional[int] = None

    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None

    category: Optional[str] = None
    spec_text: Optional[str] = None
    base_uom: Optional[str] = None
    purchase_uom: Optional[str] = None

    batch_code: str
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    qty_received: int
    units_per_case: int
    qty_units: int

    unit_cost: Optional[Decimal] = None
    line_amount: Optional[Decimal] = None
    remark: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExplainReceiveTaskLine(BaseModel):
    id: int
    task_id: int
    po_line_id: Optional[int] = None

    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    category: Optional[str] = None
    spec_text: Optional[str] = None
    base_uom: Optional[str] = None
    purchase_uom: Optional[str] = None
    units_per_case: Optional[int] = None

    batch_code: Optional[str] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    expected_qty: Optional[int] = None
    scanned_qty: int
    committed_qty: Optional[int] = None

    status: str
    remark: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExplainReceiveTask(BaseModel):
    id: int
    source_type: str
    source_id: Optional[int] = None
    po_id: Optional[int] = None
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    warehouse_id: int
    status: str
    remark: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    lines: List[ExplainReceiveTaskLine] = []

    model_config = ConfigDict(from_attributes=True)


class ExplainPurchaseOrderLine(BaseModel):
    id: int
    po_id: int
    line_no: int

    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    category: Optional[str] = None
    spec_text: Optional[str] = None
    base_uom: Optional[str] = None
    purchase_uom: Optional[str] = None
    units_per_case: Optional[int] = None

    qty_ordered: int
    qty_received: int
    status: str
    remark: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ExplainPurchaseOrder(BaseModel):
    id: int
    supplier: str
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    warehouse_id: int

    purchaser: str
    purchase_time: datetime
    remark: Optional[str] = None
    status: str

    created_at: datetime
    updated_at: datetime
    last_received_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

    lines: List[ExplainPurchaseOrderLine] = []

    model_config = ConfigDict(from_attributes=True)


class ExplainLedgerRow(BaseModel):
    id: int
    warehouse_id: int
    item_id: int
    batch_code: str

    reason: str
    reason_canon: Optional[str] = None
    sub_reason: Optional[str] = None

    ref: str
    ref_line: int

    delta: int
    after_qty: int

    occurred_at: datetime
    created_at: datetime

    trace_id: Optional[str] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class LedgerExplainOut(BaseModel):
    anchor: ExplainAnchor
    ledger: List[ExplainLedgerRow]
    receipt: ExplainReceipt
    receipt_lines: List[ExplainReceiptLine]
    receive_task: Optional[ExplainReceiveTask] = None
    purchase_order: Optional[ExplainPurchaseOrder] = None
