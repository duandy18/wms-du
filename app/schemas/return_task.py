# app/schemas/return_task.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, AliasChoices


class ReturnTaskLineOut(BaseModel):
    id: int
    task_id: int

    order_line_id: Optional[int] = None

    item_id: int
    item_name: Optional[str]
    batch_code: str

    expected_qty: Optional[int]
    picked_qty: int
    committed_qty: Optional[int]

    status: str
    remark: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ReturnTaskCreateFromOrder(BaseModel):
    warehouse_id: Optional[int] = Field(
        None,
        description="回仓仓库 ID；不传则由服务层决定（默认=原出库仓库，若不唯一则要求显式传入）",
    )
    include_zero_shipped: bool = Field(
        False,
        description="是否包含出库数量为 0 的行（通常不需要）",
    )


class ReturnTaskReceiveIn(BaseModel):
    item_id: int = Field(..., description="商品 ID")
    qty: int = Field(..., description="本次回仓数量（可正可负，用于撤销误扫）")


class ReturnTaskCommitIn(BaseModel):
    trace_id: Optional[str] = Field(
        None,
        description="用于跨表追踪的 trace_id，可选（建议填订单 trace_id）",
    )


class ReturnTaskOut(BaseModel):
    id: int
    order_id: str  # order_ref
    warehouse_id: int
    status: str
    remark: Optional[str]
    created_at: datetime
    updated_at: datetime

    lines: List[ReturnTaskLineOut] = []

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# 退货回仓作业台：order_ref 左侧上下文（台账驱动，只读）
# =========================================================
class ReturnOrderRefItem(BaseModel):
    order_ref: str
    warehouse_id: Optional[int] = None
    last_ship_at: datetime
    total_lines: int

    remaining_qty: int = Field(
        ...,
        validation_alias=AliasChoices("remaining_qty", "total_shipped_qty"),
        description="剩余可退数量（shipped - returned）",
    )


class ReturnOrderRefSummaryLine(BaseModel):
    warehouse_id: int
    item_id: int
    item_name: Optional[str] = None  # ✅ 新增：用于详情展示（作业人员视角）
    batch_code: str
    shipped_qty: int


class ReturnOrderRefSummaryOut(BaseModel):
    order_ref: str
    ship_reasons: List[str] = Field(default_factory=list)
    lines: List[ReturnOrderRefSummaryLine]


# =========================================================
# 退货回仓作业台：订单详情（只读）
# =========================================================
class ReturnOrderRefReceiverOut(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None


class ReturnOrderRefShippingOut(BaseModel):
    tracking_no: Optional[str] = None
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    status: Optional[str] = None
    shipped_at: Optional[datetime] = None
    gross_weight_kg: Optional[float] = None
    cost_estimated: Optional[float] = None
    receiver: Optional[ReturnOrderRefReceiverOut] = None
    meta: Optional[Dict[str, Any]] = None


class ReturnOrderRefDetailOut(BaseModel):
    order_ref: str
    platform: Optional[str] = None
    shop_id: Optional[str] = None
    ext_order_no: Optional[str] = None

    remaining_qty: Optional[int] = None

    shipping: Optional[ReturnOrderRefShippingOut] = None
    summary: ReturnOrderRefSummaryOut
