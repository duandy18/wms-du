# app/schemas/order.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, ConfigDict, field_validator

# ✅ 引用统一的业务枚举
from app.models.enum import OrderType, OrderStatus


# ===== 通用基类：允许 ORM、忽略多余字段 =====
class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


# ===== 行项目 入参 =====
class OrderLineIn(_Base):
    """
    行项目：支持以 item_id 或 sku 指定商品（至少一者必须提供）。
    """
    item_id: Annotated[int | None, Field(default=None, ge=1)] = None
    sku: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    qty: Annotated[int, Field(ge=1, description="数量，必须>=1")]
    price: float | None = Field(default=None, description="单价（可选）")

    @field_validator("sku")
    @classmethod
    def _trim_sku(cls, v: str | None):
        if v is None:
            return v
        s = v.strip()
        return s or None

    @field_validator("item_id", mode="after")
    @classmethod
    def _check_identity(cls, v, info):
        data = info.data
        item_id = v
        sku = data.get("sku")
        if item_id is None and not sku:
            raise ValueError("必须提供 item_id 或 sku 其中之一")
        return item_id


# ===== 创建订单 入参 =====
class OrderCreate(_Base):
    """
    创建订单（v1.0）
    - order_type：SALES / PURCHASE
    - lines：至少 1 条
    - 可选：order_no / buyer_name / platform
    """
    order_type: OrderType
    lines: list[OrderLineIn]
    order_no: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    buyer_name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    platform: Annotated[str | None, Field(default=None, min_length=1, max_length=64)] = None
    ref: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None

    @field_validator("lines")
    @classmethod
    def _lines_non_empty(cls, v: list[OrderLineIn]):
        if not v:
            raise ValueError("订单行不能为空")
        return v


# ===== 更新状态 入参 =====
class OrderStatusUpdate(_Base):
    status: OrderStatus


# ===== 出参：行项目 =====
class OrderItemOut(_Base):
    item_id: int
    qty: int
    price: float | None = None
    sku: str | None = None


# ===== 出参：订单 =====
class OrderOut(_Base):
    id: int
    order_type: OrderType
    status: OrderStatus
    lines: list[OrderItemOut] = Field(default_factory=list)

    order_no: str | None = None
    buyer_name: str | None = None
    platform: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


__all__ = [
    "OrderLineIn",
    "OrderCreate",
    "OrderStatusUpdate",
    "OrderItemOut",
    "OrderOut",
]
