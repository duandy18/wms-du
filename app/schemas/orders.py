# app/schemas/orders.py
from datetime import datetime

from pydantic import BaseModel

from app.models.orders import OrderStatus, OrderType


class OrderLineCreate(BaseModel):
    item_sku: str
    quantity: float


class OrderLineOut(OrderLineCreate):
    id: str
    order_id: str

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    order_number: str
    order_type: OrderType
    party_id: str
    order_lines: list[OrderLineCreate]


class OrderOut(BaseModel):
    id: str
    order_number: str
    order_type: OrderType
    party_id: str
    order_date: datetime
    status: OrderStatus
    order_lines: list[OrderLineOut]

    class Config:
        from_attributes = True


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# app/schemas/orders.py

# ... (保持文件顶部现有代码不变)


class OrderUpdate(BaseModel):
    order_number: str | None = None
    order_type: OrderType | None = None
    party_id: str | None = None
    status: OrderStatus | None = None
    order_lines: list[OrderLineCreate] | None = None
