"""drop po fields from return_tasks for order return receive

Revision ID: 058458be7624
Revises: 5991a9c4a5ea
Create Date: 2026-01-08 19:26:01.177343

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "058458be7624"
down_revision: Union[str, Sequence[str], None] = "5991a9c4a5ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ---- drop indexes first ----
    op.drop_index("ix_return_task_lines_po_line_id", table_name="return_task_lines")
    op.drop_index("ix_return_tasks_supplier_id", table_name="return_tasks")
    op.drop_index("ix_return_tasks_po_id", table_name="return_tasks")

    # ---- drop columns ----
    op.drop_column("return_task_lines", "po_line_id")

    op.drop_column("return_tasks", "supplier_name")
    op.drop_column("return_tasks", "supplier_id")
    op.drop_column("return_tasks", "po_id")


def downgrade() -> None:
    """Downgrade schema."""
    # ---- add columns back ----
    op.add_column(
        "return_tasks",
        sa.Column(
            "po_id",
            sa.Integer(),
            nullable=True,
            comment="关联采购单 purchase_orders.id，可为空",
        ),
    )
    op.add_column(
        "return_tasks",
        sa.Column(
            "supplier_id",
            sa.Integer(),
            nullable=True,
            comment="供应商 ID（冗余自采购单）",
        ),
    )
    op.add_column(
        "return_tasks",
        sa.Column(
            "supplier_name",
            sa.String(length=255),
            nullable=True,
            comment="供应商名称快照（冗余自采购单）",
        ),
    )
    op.add_column(
        "return_task_lines",
        sa.Column(
            "po_line_id",
            sa.Integer(),
            nullable=True,
            comment="关联采购单行 purchase_order_lines.id，可为空",
        ),
    )

    # ---- add indexes back ----
    op.create_index("ix_return_tasks_po_id", "return_tasks", ["po_id"])
    op.create_index("ix_return_tasks_supplier_id", "return_tasks", ["supplier_id"])
    op.create_index("ix_return_task_lines_po_line_id", "return_task_lines", ["po_line_id"])
