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
    订单退货回仓任务头表（Return Task）

    一个任务代表一次“订单退货回仓作业”：
    - order_id（order_ref）非空：用于关联出库台账 stock_ledger.ref（字符串）；
    - 回仓入库（库存增加）。

    状态：
    - DRAFT: 草稿 / 回仓进行中；
    - COMMITTED: 已入库，写过 ledger + stocks，不能再改；
    - CANCELLED: 作废，不再使用（不写 ledger）。
    """

    __tablename__ = "return_tasks"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    order_id: Mapped[str] = mapped_column(
        sa.String(128),
        nullable=False,
        index=True,
        comment="订单来源键（order_ref）：用于关联出库台账 stock_ledger.ref（字符串），必填",
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
        return f"<ReturnTask id={self.id} order_id={self.order_id} wh={self.warehouse_id} status={self.status}>"


class ReturnTaskLine(Base):
    """
    订单退货回仓任务行（Return Task Line）

    一行代表一个 item（自动回原批次回仓）：

    - expected_qty: 计划回仓数量（来自订单原出库数量）；
    - picked_qty: 已扫码/录入的回仓数量（累积）；
    - committed_qty: 最终确认入库数量（commit 时写入）。

    核心约束：
    - batch_code 必须由系统自动回原批次（来自出库台账），不允许人工补录。
    """

    __tablename__ = "return_task_lines"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)

    task_id: Mapped[int] = mapped_column(
        sa.Integer,
        sa.ForeignKey("return_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_line_id: Mapped[Optional[int]] = mapped_column(
        sa.BigInteger,
        nullable=True,
        index=True,
        comment="可选：关联订单行 order_lines.id（用于更强边界/追溯）",
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

    batch_code: Mapped[str] = mapped_column(
        sa.String(64),
        nullable=False,
        comment="批次编码（系统自动回原批次：来自订单出库台账，必填；不允许人工补录）",
    )

    expected_qty: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="计划回仓数量（来自订单原出库数量）",
    )

    picked_qty: Mapped[int] = mapped_column(
        sa.Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="已扫码/录入的回仓数量（可正可负，用于撤销误扫）",
    )

    committed_qty: Mapped[Optional[int]] = mapped_column(
        sa.Integer,
        nullable=True,
        comment="最终入库数量（commit 时写入）",
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
