# app/schemas/order.py
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, conint


# ---- 枚举：用 Enum，不要元组/列表 ----
class OrderType(str, Enum):
    SALES = "SALES"
    PURCHASE = "PURCHASE"


class OrderStatus(str, Enum):
    created = "created"
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"


# ---- 行项目入参 ----
class OrderLineIn(BaseModel):
    item_id: int = Field(..., ge=1)
    qty: conint(ge=1)  # 数量必须 >= 1
    price: float | None = None  # 可选，销售可填，采购也可填


# ---- 创建订单入参 ----
class OrderCreate(BaseModel):
    order_type: OrderType
    buyer_name: str | None = None
    platform: str | None = None
    lines: list[OrderLineIn]


# ---- 更新状态入参 ----
class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# ---- 出参（给前端/调用方）----
class OrderItemOut(BaseModel):
    item_id: int
    qty: int
    price: float | None = None

    model_config = dict(from_attributes=True)


class OrderOut(BaseModel):
    id: int
    order_type: OrderType
    status: OrderStatus
    buyer_name: str | None = None
    platform: str | None = None
    lines: list[OrderItemOut] = []

    # 允许用 ORM 对象直接校验（model_validate(order)）
    model_config = dict(from_attributes=True)
