# app/api/routers/orders_fulfillment_v2_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, conint


# ---------------------------------------------------------------------------
# 1) 订单拣货 v2
# ---------------------------------------------------------------------------


class PickLineIn(BaseModel):
    item_id: conint(gt=0)
    qty: conint(gt=0)
    # 终态：按行 batch_code（REQUIRED 必填；NONE 必须为 null；校验在 API 层完成）
    batch_code: Optional[str] = Field(
        default=None,
        description="批次编码：expiry-policy REQUIRED 的商品必填且非空；expiry-policy NONE 的商品必须为 null（合同校验在 API 层完成）",
    )


class PickRequest(BaseModel):
    warehouse_id: conint(gt=0) = Field(..., description="拣货仓库 ID（>0，允许 1）")
    lines: List[PickLineIn] = Field(default_factory=list)
    occurred_at: Optional[datetime] = Field(default=None, description="拣货时间（缺省为当前 UTC 时间）")


class PickResponse(BaseModel):
    item_id: int
    warehouse_id: int
    batch_code: Optional[str]
    picked: int
    stock_after: Optional[int] = None
    ref: str
    status: str
