# app/wms/procurement/contracts/inbound_receipt.py
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_serializer


UTC = timezone.utc


def _to_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class InboundReceiptLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    line_no: int

    po_line_id: Optional[int] = None
    item_id: int
    item_name: Optional[str] = None
    item_sku: Optional[str] = None

    barcode: Optional[str] = None

    # ✅ 合同双轨：lot_code 正名；batch_code 兼容字段
    lot_code: Optional[str] = None
    batch_code: Optional[str] = None

    production_date: Optional[date] = None
    expiry_date: Optional[date] = None

    # Phase M-5+：收货行终态为 uom_id + qty_input + ratio_to_base_snapshot + qty_base。
    # 旧字段 qty_received / units_per_case / qty_units 已退役，不再作为必填输出字段。
    # 为兼容旧前端/旧测试，保留字段名但改为 Optional。
    qty_received: Optional[int] = None
    units_per_case: Optional[int] = None
    qty_units: Optional[int] = None

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

    @field_serializer("created_at")
    def _ser_created_at(self, v: datetime) -> datetime:
        return _to_utc(v)

    @field_serializer("updated_at")
    def _ser_updated_at(self, v: datetime) -> datetime:
        return _to_utc(v)


class InboundReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    warehouse_id: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None

    source_type: str
    source_id: Optional[int] = None

    ref: str
    trace_id: Optional[str] = None

    status: str
    remark: Optional[str] = None

    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

    lines: List[InboundReceiptLineOut] = []

    @field_serializer("occurred_at")
    def _ser_occurred_at(self, v: datetime) -> datetime:
        return _to_utc(v)

    @field_serializer("created_at")
    def _ser_created_at(self, v: datetime) -> datetime:
        return _to_utc(v)

    @field_serializer("updated_at")
    def _ser_updated_at(self, v: datetime) -> datetime:
        return _to_utc(v)
