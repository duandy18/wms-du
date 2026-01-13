# app/schemas/inbound_receipt.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_serializer


class InboundReceiptLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    line_no: int

    po_line_id: Optional[int] = None
    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None

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

    @field_serializer("unit_cost")
    def _ser_unit_cost(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None

    @field_serializer("line_amount")
    def _ser_line_amount(self, v: Optional[Decimal]) -> Optional[str]:
        return str(v) if v is not None else None


class InboundReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    lines: List[InboundReceiptLineOut] = []
