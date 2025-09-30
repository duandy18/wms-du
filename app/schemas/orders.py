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
