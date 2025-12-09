# app/schemas/internal_outbound.py
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class InternalOutboundLineOut(BaseModel):
    id: int
    doc_id: int
    line_no: int
    item_id: int
    batch_code: Optional[str] = None
    requested_qty: int
    confirmed_qty: Optional[int] = None
    uom: Optional[str] = None
    note: Optional[str] = None
    extra_meta: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class InternalOutboundDocOut(BaseModel):
    id: int
    warehouse_id: int
    doc_no: str
    doc_type: str
    status: str

    recipient_name: Optional[str] = None
    recipient_id: Optional[int] = None
    recipient_type: Optional[str] = None
    recipient_note: Optional[str] = None

    note: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    confirmed_by: Optional[int] = None
    confirmed_at: Optional[datetime] = None
    canceled_by: Optional[int] = None
    canceled_at: Optional[datetime] = None

    trace_id: Optional[str] = None
    extra_meta: Optional[dict[str, Any]] = None

    lines: List[InternalOutboundLineOut] = []

    model_config = ConfigDict(from_attributes=True)


# --------- 输入模型 ---------


class InternalOutboundCreateDocIn(BaseModel):
    warehouse_id: int
    doc_type: str
    recipient_name: str
    recipient_type: Optional[str] = None
    recipient_note: Optional[str] = None
    note: Optional[str] = None
    trace_id: Optional[str] = None


class InternalOutboundUpsertLineIn(BaseModel):
    item_id: int
    qty: int
    batch_code: Optional[str] = None
    uom: Optional[str] = None
    note: Optional[str] = None


class InternalOutboundConfirmIn(BaseModel):
    # 预留 trace_id 入参；当前 InternalOutboundService 会自己生成 trace_id，
    # 后续如需外部显式传入，可在 service 里接入。
    trace_id: Optional[str] = None
