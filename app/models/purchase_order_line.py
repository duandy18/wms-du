# app/models/purchase_order_line.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from .purchase_order import PurchaseOrder


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        sa.UniqueConstraint(
            "po_id",
            "line_no",
            name="uq_purchase_order_lines_po_id_line_no",
        ),
    )

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    po_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_no: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    item_name: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    item_sku: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, index=True)

    spec_text: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    base_uom: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    purchase_uom: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    # ✅ 采购单价（按 base_uom 计价的单价快照；允许为空，聚合金额时需按 0 处理）
    supply_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(12, 2), nullable=True)

    # ✅ 单位换算（方案 A）：upc 非空（默认 1），base 唯一事实
    units_per_case: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="换算因子：每 1 采购单位包含多少最小单位（>0）",
    )

    # 采购单位订购量（输入快照/展示口径）
    qty_ordered: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        comment="订购数量（采购单位口径，>0）",
    )

    # ✅ 最小单位订购量（事实字段）
    qty_ordered_base: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="订购数量（最小单位 base，事实字段）",
    )

    # ✅ 折扣（整行减免金额 + 说明）
    discount_amount: Mapped[Decimal] = mapped_column(
        sa.Numeric(14, 2),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        comment="整行减免金额（>=0）",
    )
    discount_note: Mapped[Optional[str]] = mapped_column(
        sa.Text,
        nullable=True,
        comment="折扣说明（可选）",
    )

    remark: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    order: Mapped["PurchaseOrder"] = relationship(
        "PurchaseOrder",
        back_populates="lines",
    )

    def __repr__(self) -> str:
        return (
            f"<POLine id={self.id} po_id={self.po_id} "
            f"line_no={self.line_no} item_id={self.item_id} "
            f"ordered={self.qty_ordered}/{self.qty_ordered_base} "
            f"upc={self.units_per_case} "
            f"price={self.supply_price} discount={self.discount_amount}>"
        )
