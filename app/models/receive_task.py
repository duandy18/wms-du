# app/models/receive_task.py
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ReceiveTask(Base):
    """
    收货任务头表（Receive Task）

    一个任务代表一次“收货作业”，可以来源于：
    - 某张采购单（source_type=PO, source_id=po_id）
    - 某个订单/退货单（source_type=ORDER, source_id=order_id）
    - 手工/初始库存（source_type=OPENING / MANUAL）
    """

    __tablename__ = "receive_tasks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    # 来源
    source_type: Mapped[str] = mapped_column(sa.String(32), nullable=False, server_default="PO")
    source_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, index=True)

    # 兼容 PO 模式
    po_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, index=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True)
    supplier_name: Mapped[Optional[str]] = mapped_column(sa.String(255))

    warehouse_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)

    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    remark: Mapped[Optional[str]] = mapped_column(sa.String(255))

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 关系：一头多行
    lines: Mapped[List["ReceiveTaskLine"]] = relationship(
        "ReceiveTaskLine",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ReceiveTask id={self.id} src={self.source_type}:{self.source_id} "
            f"po_id={self.po_id} wh={self.warehouse_id} status={self.status}>"
        )


class ReceiveTaskLine(Base):
    """
    收货任务行（Receive Task Line）

    一行 = 一条“采购行快照 + 收货行为信息”：
    - 采购行快照：item_xxx / spec / uom / units_per_case 等
    - 收货数量：expected/scanned/committed
    - 批次：batch_code + production_date + expiry_date
    """

    __tablename__ = "receive_task_lines"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    task_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("receive_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    po_line_id: Mapped[Optional[int]] = mapped_column(sa.Integer, nullable=True, index=True)

    # --- 采购行快照（来自 purchase_order_lines） ---
    item_id: Mapped[int] = mapped_column(sa.Integer, nullable=False, index=True)
    item_name: Mapped[Optional[str]] = mapped_column(sa.String(255))
    item_sku: Mapped[Optional[str]] = mapped_column(sa.String(64))
    category: Mapped[Optional[str]] = mapped_column(sa.String(64))
    spec_text: Mapped[Optional[str]] = mapped_column(sa.String(255))
    base_uom: Mapped[Optional[str]] = mapped_column(sa.String(32))
    purchase_uom: Mapped[Optional[str]] = mapped_column(sa.String(32))
    units_per_case: Mapped[Optional[int]] = mapped_column(sa.Integer)

    # --- 批次 / 日期信息（收货时才能知道） ---
    batch_code: Mapped[Optional[str]] = mapped_column(sa.String(64))
    production_date: Mapped[Optional[date]] = mapped_column(sa.Date)
    expiry_date: Mapped[Optional[date]] = mapped_column(sa.Date)

    # --- 收货数量 ---
    expected_qty: Mapped[Optional[int]] = mapped_column(sa.Integer)
    scanned_qty: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=0, server_default="0"
    )
    committed_qty: Mapped[Optional[int]] = mapped_column(sa.Integer)

    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, default="DRAFT", server_default="DRAFT"
    )
    remark: Mapped[Optional[str]] = mapped_column(sa.String(255))

    # 关系：多行 -> 一头
    task: Mapped["ReceiveTask"] = relationship(
        "ReceiveTask",
        back_populates="lines",
    )

    def __repr__(self) -> str:
        return (
            f"<ReceiveTaskLine id={self.id} task_id={self.task_id} "
            f"item_id={self.item_id} expected={self.expected_qty} "
            f"scanned={self.scanned_qty} committed={self.committed_qty} "
            f"status={self.status}>"
        )
