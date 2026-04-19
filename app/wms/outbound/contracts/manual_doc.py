# app/wms/outbound/contracts/manual_doc.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ManualOutboundDocLineOut(BaseModel):
    """
    手动出库单据行：来源层
    - 不承载 batch / confirmed_qty
    """
    model_config = ConfigDict(extra="ignore")

    id: int
    line_no: int
    item_id: int
    requested_qty: int
    remark: Optional[str] = None


class ManualOutboundDocOut(BaseModel):
    """
    手动出库单据头：来源层
    状态只保留 DRAFT / RELEASED / VOIDED
    """
    model_config = ConfigDict(extra="ignore")

    id: int
    warehouse_id: int
    doc_no: str
    doc_type: str
    status: str

    recipient_name: Optional[str] = None
    recipient_id: Optional[int] = None
    recipient_type: Optional[str] = None
    recipient_note: Optional[str] = None

    remark: Optional[str] = None

    created_by: Optional[int] = None
    created_at: datetime

    released_by: Optional[int] = None
    released_at: Optional[datetime] = None

    voided_by: Optional[int] = None
    voided_at: Optional[datetime] = None

    lines: List[ManualOutboundDocLineOut] = Field(default_factory=list)


class ManualOutboundDocCreateLineIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: int = Field(..., ge=1)
    requested_qty: int = Field(..., gt=0)
    remark: Optional[str] = Field(default=None, max_length=255)


class ManualOutboundDocCreateIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    warehouse_id: int = Field(..., ge=1)
    doc_type: str = Field(..., min_length=1, max_length=64)

    recipient_name: str = Field(..., min_length=1, max_length=255)
    recipient_type: Optional[str] = Field(default=None, max_length=64)
    recipient_note: Optional[str] = Field(default=None, max_length=255)

    remark: Optional[str] = Field(default=None, max_length=255)

    lines: List[ManualOutboundDocCreateLineIn] = Field(default_factory=list)
