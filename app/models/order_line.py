from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderLine(Base):
    """订单行（以数据库为准的薄模型；常用于保留历史/导入）"""

    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("orders.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # 保持与现库一致
    req_qty: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_order_lines_order_id", "order_id"),
        Index("ix_order_lines_item", "item_id"),
        {"info": {"skip_autogen": True}},
    )

    def __repr__(self) -> str:
        return f"<OrderLine id={self.id} order_id={self.order_id} item={self.item_id} req={self.req_qty}>"
