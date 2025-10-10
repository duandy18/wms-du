from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.stock import Stock


class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def _get_available(self, sku: str) -> int:
        row = self.db.execute(select(Stock).where(Stock.item_sku == sku)).scalars().first()
        return int(row.quantity) if row else 0

    def _deduct(self, sku: str, quantity: int):
        row = (
            self.db.execute(select(Stock).where(Stock.item_sku == sku).with_for_update())
            .scalars()
            .first()
        )
        if not row or row.quantity < quantity:
            raise ValueError("Insufficient stock for item")
        row.quantity -= quantity
        self.db.flush()

    def create_order(self, *, order_data: dict[str, Any]) -> int:
        platform = order_data["platform"]
        platform_order_id = order_data["platform_order_id"]
        customer_name = order_data["customer_name"]
        items = order_data.get("items", [])

        exists = self.db.execute(
            select(Order.id).where(
                Order.platform == platform,
                Order.platform_order_id == platform_order_id,
            )
        ).first()
        if exists:
            raise IntegrityError("duplicate key", params=None, orig=None)

        try:
            # 1) 预检查库存
            for it in items:
                if self._get_available(it["sku"]) < int(it["quantity"]):
                    raise ValueError("Insufficient stock for item")

            # 2) 扣减库存
            for it in items:
                self._deduct(it["sku"], int(it["quantity"]))

            # 3) 落库：订单与明细
            order = Order(
                platform=platform,
                platform_order_id=platform_order_id,
                customer_name=customer_name,
            )
            self.db.add(order)
            self.db.flush()

            for it in items:
                self.db.add(
                    OrderItem(
                        order_id=order.id,
                        sku=it["sku"],
                        quantity=int(it["quantity"]),
                    )
                )

            self.db.commit()
            return order.id
        except Exception:
            self.db.rollback()
            raise
