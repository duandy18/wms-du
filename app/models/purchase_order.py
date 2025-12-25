# app/models/purchase_order.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.purchase_order_line import PurchaseOrderLine


class PurchaseOrder(Base):
    """
    采购单头表（Phase 2：唯一形态）

    说明：
    - 不再保存 item_id / qty_ordered / qty_received / unit_cost 等行级信息；
    - 所有数量与金额都以行表（purchase_order_lines）为事实来源；
    - 头表只负责表达单据级别信息：
        * 供应商 / 仓库
        * 采购人 / 采购时间
        * 汇总金额
        * 状态
        * 时间信息
        * 备注（可选）
    """

    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    # 供应商（自由文本 + 主数据 + 快照）
    supplier: Mapped[str] = mapped_column(sa.String(100), nullable=False, index=True)

    supplier_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        index=True,
        comment="FK → suppliers.id，可为空",
    )
    supplier_name: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="下单时的供应商名称快照，通常来自 suppliers.name",
    )

    # 仓库
    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)

    # 采购人（必填）
    purchaser: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        comment="采购人姓名或编码",
    )

    # 采购时间（必填）
    purchase_time: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        comment="采购单创建/确认时间",
    )

    # 汇总金额（通常 = 行金额之和）
    total_amount: Mapped[Optional[Decimal]] = mapped_column(
        sa.Numeric(14, 2),
        nullable=True,
        comment="PO 汇总金额，由行表 line_amount 聚合",
    )

    # 状态：CREATED / PARTIAL / RECEIVED / CLOSED
    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="CREATED",
    )

    # 头部备注（可选）
    remark: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="采购单头部备注（可选）",
    )

    # 时间信息
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
    last_received_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    # 多行关联
    lines: Mapped[List["PurchaseOrderLine"]] = relationship(
        "PurchaseOrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        sa.Index(
            "ix_purchase_orders_wh_status",
            "warehouse_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PO id={self.id} supplier={self.supplier!r} "
            f"wh={self.warehouse_id} purchaser={self.purchaser!r} "
            f"status={self.status} total_amount={self.total_amount}>"
        )
