# app/wms/outbound/contracts/outbound_summary.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OutboundSummaryRowOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: int
    event_no: str
    event_type: str
    source_type: str
    source_ref: Optional[str] = None

    warehouse_id: int
    occurred_at: datetime
    committed_at: datetime
    trace_id: str
    status: str

    created_by: Optional[int] = None
    remark: Optional[str] = None

    lines_count: int = 0
    total_qty_outbound: int = 0


class OutboundSummaryLineOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    event_id: int
    ref_line: int
    item_id: int
    qty_outbound: int
    lot_id: int
    lot_code_snapshot: Optional[str] = None
    order_line_id: Optional[int] = None
    manual_doc_line_id: Optional[int] = None
    item_name_snapshot: Optional[str] = None
    item_sku_snapshot: Optional[str] = None
    item_spec_snapshot: Optional[str] = None
    remark: Optional[str] = None
    created_at: datetime


class OutboundSummaryListOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: List[OutboundSummaryRowOut] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class OutboundSummaryDetailOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: OutboundSummaryRowOut
    lines: List[OutboundSummaryLineOut] = Field(default_factory=list)
