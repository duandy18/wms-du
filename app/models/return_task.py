# app/models/return_task.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ReturnTask(Base):
    """
    采购退货任务头表（Return Task）

    一个任务代表一次“退货作业”：
    - 通常关联某张采购单（po_id 非空）；
    - 从仓库退回给供应商（库存减少）。

    状态：
    - DRAFT: 草稿 / 退货进行中，只能改 expected/picked；
    - COMMITTED: 已出库，写过 ledger + stocks，不能再改；
    - CANCELLED: 作废，不再使用（不写 ledger）。
    """

    __tablename__ = "return_tasks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    po_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        index=True,
        comment="关联采购单 purchase_orders.id，可为空",
    )

    supplier_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        index=True,
        comment="供应商 ID（冗余自采购单）",
    )
    supplier_name: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="供应商名称快照（冗余自采购单）",
    )

    warehouse_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        index=True,
        comment="退货仓库 ID",
    )

    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="DRAFT",
        comment="DRAFT / COMMITTED / CANCELLED",
    )

    remark: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="整单备注",
    )

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

    lines: Mapped[List["ReturnTaskLine"]] = relationship(
        "ReturnTaskLine",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ReturnTask id={self.id} po_id={self.po_id} "
            f"wh={self.warehouse_id} status={self.status}>"
        )


class ReturnTaskLine(Base):
    """
    采购退货任务行（Return Task Line）

    一行代表一个 item 在本任务中的退货情况：

    - expected_qty: 计划退货数量（来自采购单已收数量或人工录入）；
    - picked_qty: 实际从仓内挑出的退货数量（扫码/拣货累积）；
    - committed_qty: 最终确认出库数量（commit 时写入）。
    """

    __tablename__ = "return_task_lines"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    task_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("return_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    po_line_id: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        index=True,
        comment="关联采购单行 purchase_order_lines.id，可为空",
    )

    item_id: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        index=True,
        comment="商品 ID",
    )
    item_name: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="商品名称快照（可选）",
    )

    batch_code: Mapped[Optional[str]] = mapped_column(
        sa.String(64),
        nullable=True,
        comment="批次编码（可选，不强制）",
    )

    expected_qty: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="计划退货数量（来自 PO 已收数量或人工录入）",
    )
    picked_qty: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="已拣选/扫码准备退货的数量（可正可负）",
    )
    committed_qty: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="最终出库数量（commit 时写入）",
    )

    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        default="DRAFT",
        server_default="DRAFT",
        comment="DRAFT / MATCHED / MISMATCH / COMMITTED",
    )

    remark: Mapped[Optional[str]] = mapped_column(
        sa.String(255),
        nullable=True,
        comment="行备注",
    )

    task: Mapped["ReturnTask"] = relationship(
        "ReturnTask",
        back_populates="lines",
    )

    def __repr__(self) -> str:
        return (
            f"<ReturnTaskLine id={self.id} task_id={self.task_id} "
            f"item_id={self.item_id} expected={self.expected_qty} "
            f"picked={self.picked_qty} committed={self.committed_qty} "
            f"status={self.status}>"
        )
