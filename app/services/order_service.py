# app/services/order_service.py
from __future__ import annotations
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.order_item import OrderItem
from app.models.item import Item
from app.models.stock import Stock

# ---------------- 允许 None 起始态的状态机校验（用于订单/快照流） ----------------
LEGAL_STATE_MAP = {
    ("PAID", "ALLOCATED"),
    ("ALLOCATED", "SHIPPED"),
    ("SHIPPED", "COMPLETED"),
    ("PAID", "CANCELED"),
    ("ALLOCATED", "CANCELED"),
    ("SHIPPED", "CANCELED"),
}
INITIAL_ALLOWED = {"PAID", "ALLOCATED"}

def assert_legal_transition(from_state: str | None, to_state: str) -> None:
    f = (from_state or "").upper() or None
    t = (to_state or "").upper()
    if f is None:
        if t in INITIAL_ALLOWED:
            return
        raise ValueError("ILLEGAL_TRANSITION")
    if (f, t) not in LEGAL_STATE_MAP:
        raise ValueError("ILLEGAL_TRANSITION")

# ---------------------------------------------------------------------------

class OrderService:
    def __init__(self, db: Session):
        self.db = db

    # 汇总某 SKU 可用量（按 items.sku → stocks.qty 汇总）
    def _get_available(self, sku: str) -> int:
        q = (
            self.db.query(func.coalesce(func.sum(Stock.qty), 0))
            .join(Item, Item.id == Stock.item_id)
            .filter(Item.sku == sku)
        )
        qty = q.scalar() or 0
        return int(qty)

    # 简易扣减：按同 SKU 的各库位大→小逐个扣
    def _deduct(self, sku: str, quantity: int):
        to_deduct = int(quantity)
        rows = (
            self.db.query(Stock)
            .join(Item, Item.id == Stock.item_id)
            .filter(Item.sku == sku, Stock.qty > 0)
            .order_by(Stock.qty.desc(), Stock.id.asc())
            .with_for_update()
            .all()
        )
        for st in rows:
            if to_deduct <= 0:
                break
            take = min(st.qty, to_deduct)
            st.qty -= take
            to_deduct -= take
        if to_deduct > 0:
            raise ValueError("Insufficient stock for item")
        self.db.flush()

    def create_order(self, *, order_data: dict[str, Any]) -> int:
        """
        统一到内部字段：
        - 生成 order_no = f"{platform}-{platform_order_id}"
        - order_type 固定 'SALES'，status 固定 'CONFIRMED'
        - 允许 from_state 为 None 的初始流转到 'CONFIRMED'
        """
        platform = order_data["platform"]
        platform_order_id = order_data["platform_order_id"]
        customer_name = order_data.get("customer_name")
        items = order_data.get("items", [])

        order_no = f"{platform}-{platform_order_id}"

        # 幂等性：同 order_no 不可重复
        exists = self.db.execute(select(Order.id).where(Order.order_no == order_no)).first()
        if exists:
            raise IntegrityError("duplicate key", params=None, orig=None)

        try:
            # 预检查库存
            for it in items:
                if self._get_available(it["sku"]) < int(it["quantity"]):
                    raise ValueError("Insufficient stock for item")

            # 扣减
            for it in items:
                self._deduct(it["sku"], int(it["quantity"]))

            # 状态机：None -> CONFIRMED 视为首次落地（放行）
            assert_legal_transition(None, "CONFIRMED")

            # 落库：订单与明细
            order = Order(
                order_no=order_no,
                order_type="SALES",
                status="CONFIRMED",
                customer_name=customer_name,
                total_amount=0,
            )
            self.db.add(order)
            self.db.flush()

            for it in items:
                self.db.add(
                    OrderItem(
                        order_id=order.id,
                        item_id=self.db.query(Item.id).filter(Item.sku == it["sku"]).scalar(),
                        qty=int(it["quantity"]),
                        unit_price=0,
                        line_amount=0,
                    )
                )

            self.db.commit()
            return order.id
        except Exception:
            self.db.rollback()
            raise
