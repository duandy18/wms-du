"""tighten order return receive constraints

Revision ID: b11e8a98b164
Revises: 058458be7624
Create Date: 2026-01-08 19:31:37.419101

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b11e8a98b164"
down_revision: Union[str, Sequence[str], None] = "058458be7624"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    null_order = bind.execute(sa.text("select count(*) from return_tasks where order_id is null")).scalar()
    if int(null_order or 0) != 0:
        raise RuntimeError(
            f"cannot set return_tasks.order_id NOT NULL: found {null_order} rows with order_id is null"
        )

    null_batch = bind.execute(
        sa.text("select count(*) from return_task_lines where batch_code is null or btrim(batch_code)=''")
    ).scalar()
    if int(null_batch or 0) != 0:
        raise RuntimeError(
            f"cannot set return_task_lines.batch_code NOT NULL: found {null_batch} rows with null/blank batch_code"
        )

    # ---- NOT NULL ----
    op.alter_column("return_tasks", "order_id", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column(
        "return_task_lines",
        "batch_code",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    # ---- comments (consistency) ----
    op.execute(
        sa.text(
            "COMMENT ON COLUMN return_tasks.order_id IS "
            "'关联订单 orders.id（订单退货回仓任务来源，必填）'"
        )
    )
    op.execute(
        sa.text(
            "COMMENT ON COLUMN return_task_lines.batch_code IS "
            "'批次编码（系统自动回原批次：来自订单出库台账，必填；不允许人工补录）'"
        )
    )
    op.execute(sa.text("COMMENT ON COLUMN return_task_lines.expected_qty IS '计划回仓数量（来自订单原出库数量）'"))
    op.execute(
        sa.text("COMMENT ON COLUMN return_task_lines.picked_qty IS '已扫码/录入的回仓数量（可正可负，用于撤销误扫）'")
    )
    op.execute(sa.text("COMMENT ON COLUMN return_task_lines.committed_qty IS '最终入库数量（commit 时写入）'"))


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("return_task_lines", "batch_code", existing_type=sa.String(length=64), nullable=True)
    op.alter_column("return_tasks", "order_id", existing_type=sa.BigInteger(), nullable=True)

    op.execute(sa.text("COMMENT ON COLUMN return_tasks.order_id IS '关联订单 orders.id（订单退货回仓任务来源）'"))
    op.execute(sa.text("COMMENT ON COLUMN return_task_lines.batch_code IS '批次编码（可选，不强制）'"))
