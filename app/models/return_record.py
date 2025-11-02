# app/models/return_record.py
from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import DateTime, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReturnRecord(Base):
    """
    退货记录（强契约·UTC 入库）
    - 建议：DB 层存 UTC，展示层再转 Asia/Shanghai(+08:00)
    """
    __tablename__ = "return_records"
    __table_args__ = (
        Index("ix_return_records_order", "order_id"),
        Index("ix_return_records_product", "product_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    order_id: Mapped[str] = mapped_column(String, nullable=False, comment="关联的订单ID")
    product_id: Mapped[str] = mapped_column(String, nullable=False, comment="退货产品ID")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="退货数量")
    reason: Mapped[str | None] = mapped_column(String, nullable=True, comment="退货原因")

    # 具时区时间；默认写入 UTC
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="记录创建时间(UTC)",
    )

    def __repr__(self) -> str:
        return (
            f"<ReturnRecord id={self.id} order_id={self.order_id!r} "
            f"product_id={self.product_id!r} qty={self.quantity}>"
        )
