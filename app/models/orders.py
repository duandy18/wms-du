import enum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class OrderType(enum.Enum):
    PURCHASE = "purchase"  # 采购订单 (PO)
    SALES = "sales"  # 销售订单 (SO)


class OrderStatus(enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    COMPLETE = "complete"
    CANCELED = "canceled"


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, index=True)
    order_number = Column(String, unique=True, index=True)
    order_type = Column(Enum(OrderType), nullable=False)

    # 关联供应商或客户
    party_id = Column(String, ForeignKey("parties.id"))

    order_date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(Enum(OrderStatus), default=OrderStatus.DRAFT)

    # 关系字段
    party = relationship("Party")
    order_lines = relationship("OrderLine", back_populates="order", cascade="all, delete-orphan")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id = Column(String, primary_key=True, index=True)

    # 关联到父级订单
    order_id = Column(String, ForeignKey("orders.id"), index=True)
    # 关联到具体的物料
    item_sku = Column(String, ForeignKey("items.sku"), index=True)

    quantity = Column(Float, nullable=False)

    # 关系字段
    order = relationship("Order", back_populates="order_lines")
    item = relationship("Item")
