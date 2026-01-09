"""add order_id to return_tasks for order return receive

Revision ID: 5991a9c4a5ea
Revises: bc1a504aa240
Create Date: 2026-01-08 19:12:56.356434

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5991a9c4a5ea"
down_revision: Union[str, Sequence[str], None] = "bc1a504aa240"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # return_tasks: add order_id
    op.add_column(
        "return_tasks",
        sa.Column(
            "order_id",
            sa.BigInteger(),
            nullable=True,
            comment="关联订单 orders.id（订单退货回仓任务来源）",
        ),
    )
    op.create_index("ix_return_tasks_order_id", "return_tasks", ["order_id"])

    # return_task_lines: add order_line_id
    op.add_column(
        "return_task_lines",
        sa.Column(
            "order_line_id",
            sa.BigInteger(),
            nullable=True,
            comment="可选：关联订单行 order_lines.id",
        ),
    )
    op.create_index(
        "ix_return_task_lines_order_line_id",
        "return_task_lines",
        ["order_line_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_return_task_lines_order_line_id", table_name="return_task_lines")
    op.drop_column("return_task_lines", "order_line_id")

    op.drop_index("ix_return_tasks_order_id", table_name="return_tasks")
    op.drop_column("return_tasks", "order_id")
