# app/wms/outbound/contracts/manual_submit.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ManualOutboundSubmitLineIn(BaseModel):
    """
    手动出库提交：单行实际出库事实
    """
    model_config = ConfigDict(extra="forbid")

    manual_doc_line_id: int = Field(..., ge=1)
    item_id: int = Field(..., ge=1)
    qty_outbound: int = Field(..., gt=0)
    lot_id: int = Field(..., ge=1)
    remark: Optional[str] = Field(default=None, max_length=255)


class ManualOutboundSubmitIn(BaseModel):
    """
    手动出库提交：整单请求体
    """
    model_config = ConfigDict(extra="forbid")

    remark: Optional[str] = Field(default=None, max_length=255)
    lines: List[ManualOutboundSubmitLineIn] = Field(default_factory=list)


class ManualOutboundSubmitOut(BaseModel):
    """
    手动出库提交：结果
    """
    model_config = ConfigDict(extra="ignore")

    status: str
    event_id: int
    trace_id: str
    event_type: str = "OUTBOUND"
    source_type: str = "MANUAL"
    source_ref: str
    warehouse_id: int
    occurred_at: datetime
    lines_count: int
