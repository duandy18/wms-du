# app/api/routers/debug_trace_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class TraceEventModel(BaseModel):
    ts: Optional[datetime] = Field(None, description="事件时间戳（可能为空）")
    source: str = Field(
        ..., description="事件来源，例如 ledger / outbound / audit 等"
    )
    kind: str = Field(..., description="事件类型 / 动作名")
    ref: Optional[str] = Field(None, description="业务 ref（订单号 等）")
    summary: str = Field(..., description="人类可读的事件摘要（向后兼容字段）")
    raw: dict[str, Any] = Field(..., description="原始字段明细（调试用）")

    trace_id: Optional[str] = Field(
        None, description="trace_id（通常与请求参数相同，用于前端直接使用）"
    )
    warehouse_id: Optional[int] = Field(None, description="仓库 ID（若事件包含该维度）")
    item_id: Optional[int] = Field(None, description="商品 ID（若事件包含该维度）")
    batch_code: Optional[str] = Field(None, description="批次编码（若事件包含该维度）")
    movement_type: Optional[str] = Field(
        None, description="标准化动作类型：INBOUND/OUTBOUND/COUNT/ADJUST/RETURN/UNKNOWN"
    )
    message: Optional[str] = Field(None, description="人类可读摘要（前端 Timeline 优先展示）")
    reason: Optional[str] = Field(None, description="原始 reason 字段（例如台账 reason）")


class TraceResponseModel(BaseModel):
    trace_id: str
    warehouse_id: Optional[int] = Field(
        None, description="若指定，则 events 已按该 warehouse 过滤（但保留无仓的全局事件）"
    )
    events: List[TraceEventModel]
