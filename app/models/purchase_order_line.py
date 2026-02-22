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
        # ✅ DB 已存在的约束：折扣非负
        sa.CheckConstraint(
            "discount_amount >= 0",
            name="ck_po_lines_discount_amount_nonneg",
        ),
        # ✅ DB 已存在的约束：事实数量必须为正
        sa.CheckConstraint(
            "qty_ordered_base > 0",
            name="ck_po_lines_qty_ordered_base_positive",
        ),
        # ✅ DB 已存在的约束：输入痕迹存在时必须可解释
        sa.CheckConstraint(
            """
            qty_ordered_case_input IS NULL
            OR (
                case_ratio_snapshot IS NOT NULL
                AND qty_ordered_base = (qty_ordered_case_input * case_ratio_snapshot)
            )
            """,
            name="ck_po_line_case_input_valid",
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

    # ✅ 与 DB 对齐：item_id 已有 fk_po_line_item -> items.id (RESTRICT)
    item_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ✅ 快照/展示字段（历史兼容：当前仍允许为空；后续可迁移为 NOT NULL + *_snapshot 命名）
    item_name: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    item_sku: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True, index=True)
    spec_text: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)

    # ✅ 历史遗留字段：保留但不再作为“事实单位”
    base_uom: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    # ✅ 新合同字段：事实单位快照（唯一口径，NOT NULL）
    uom_snapshot: Mapped[str] = mapped_column(sa.String(32), nullable=False)

    # ✅ 包装结构快照（允许为空：未治理）
    case_ratio_snapshot: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    case_uom_snapshot: Mapped[Optional[str]] = mapped_column(sa.String(16), nullable=True)

    # ✅ 输入痕迹（可空）：按“箱/采购口径”录入时保留输入数量
    qty_ordered_case_input: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)

    # ✅ 采购单价（允许为空，聚合金额时按 0 处理）
    supply_price: Mapped[Optional[Decimal]] = mapped_column(sa.Numeric(12, 2), nullable=True)

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
            f"base={self.qty_ordered_base} "
            f"case_in={self.qty_ordered_case_input} "
            f"ratio={self.case_ratio_snapshot} "
            f"price={self.supply_price} discount={self.discount_amount}>"
        )
