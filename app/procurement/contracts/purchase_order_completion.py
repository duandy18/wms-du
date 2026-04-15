# app/procurement/contracts/purchase_order_completion.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PurchaseOrderCompletionLineOut(BaseModel):
    po_line_id: int
    line_no: int

    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    spec_text: Optional[str] = None

    purchase_uom_id_snapshot: int
    purchase_uom_name_snapshot: str
    purchase_ratio_to_base_snapshot: int
    qty_ordered_input: int
    qty_ordered_base: int

    qty_received_base: int
    qty_remaining_base: int
    line_completion_status: str
    last_received_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderCompletionListItemOut(BaseModel):
    po_id: int
    po_no: str
    po_status: str

    warehouse_id: int
    supplier_id: int
    supplier_name: str
    purchaser: str
    purchase_time: datetime
    total_amount: Optional[Decimal] = None

    po_line_id: int
    line_no: int

    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None
    spec_text: Optional[str] = None

    purchase_uom_id_snapshot: int
    purchase_uom_name_snapshot: str
    purchase_ratio_to_base_snapshot: int
    qty_ordered_input: int
    qty_ordered_base: int

    qty_received_base: int
    qty_remaining_base: int
    line_completion_status: str
    last_received_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderCompletionEventOut(BaseModel):
    event_id: int
    event_no: str
    trace_id: str
    source_ref: Optional[str] = None
    occurred_at: datetime

    po_line_id: int
    line_no: int
    item_id: int

    qty_base: int
    lot_code: Optional[str] = None
    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderCompletionSummaryOut(BaseModel):
    po_id: int
    po_no: str
    po_status: str

    warehouse_id: int
    supplier_id: int
    supplier_name: str
    purchaser: str
    purchase_time: datetime
    total_amount: Optional[Decimal] = None

    total_ordered_base: int
    total_received_base: int
    total_remaining_base: int
    completion_status: str
    last_received_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderCompletionDetailOut(BaseModel):
    summary: PurchaseOrderCompletionSummaryOut
    lines: List[PurchaseOrderCompletionLineOut] = Field(default_factory=list)
    receipt_events: List[PurchaseOrderCompletionEventOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
