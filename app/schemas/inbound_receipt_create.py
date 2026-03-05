# app/schemas/inbound_receipt_create.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InboundReceiptCreateIn(BaseModel):
    """
    Receipt 创建入口（最小闭环：先支持 PO -> DRAFT receipt）

    合同口径：
    - source_type: "PO"（兼容 "PURCHASE_ORDER"/"purchase_order" 等输入，router 内会归一化）
    - source_id: po_id

    occurred_at:
    - 可选；未传则后端用 now(UTC)
    """

    model_config = ConfigDict(extra="ignore")

    source_type: str = Field(..., description="PO / ORDER / OTHER（当前仅支持 PO）")
    source_id: int = Field(..., description="source id（PO 时为 po_id）")

    occurred_at: Optional[datetime] = Field(None, description="发生时间（可选，默认 now）")

    # 预留：未来 OTHER/手工单据可能会用到；当前 PO 模式忽略这些输入
    warehouse_id: Optional[int] = None
    remark: Optional[str] = None
