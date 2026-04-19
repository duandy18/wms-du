# app/wms/outbound/contracts/order_submit.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class OrderOutboundSubmitLineIn(BaseModel):
    """
    订单出库提交：单行实际出库事实
    """
    model_config = ConfigDict(extra="ignore")

    order_line_id: int = Field(..., ge=1)
    item_id: int = Field(..., ge=1)
    qty_outbound: int = Field(..., gt=0)
    lot_id: int = Field(..., ge=1)
    lot_code: Optional[str] = Field(default=None, min_length=1, max_length=64)
    remark: Optional[str] = Field(default=None, max_length=255)


class OrderOutboundSubmitIn(BaseModel):
    """
    订单出库提交：整单请求体
    """
    model_config = ConfigDict(extra="ignore")

    warehouse_id: int = Field(..., ge=1)
    remark: Optional[str] = Field(default=None, max_length=255)
    lines: List[OrderOutboundSubmitLineIn] = Field(default_factory=list)


class OrderOutboundSubmitOut(BaseModel):
    """
    订单出库提交：结果
    """
    model_config = ConfigDict(extra="ignore")

    status: str
    event_id: int
    trace_id: str
    event_type: str = "OUTBOUND"
    source_type: str = "ORDER"
    source_ref: str
    warehouse_id: int
    occurred_at: datetime
    lines_count: int
