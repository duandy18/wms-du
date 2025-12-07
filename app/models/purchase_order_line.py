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

    category: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)

    spec_text: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    base_uom: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)
    purchase_uom: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    supply_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(12, 2), nullable=True)
    retail_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(12, 2), nullable=True)
    promo_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(12, 2), nullable=True)
    min_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(12, 2), nullable=True)

    qty_cases: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    units_per_case: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    qty_ordered: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    qty_received: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    line_amount: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="CREATED",
        server_default="CREATED",
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
            f"qty={self.qty_ordered}/{self.qty_received} status={self.status}>"
        )
