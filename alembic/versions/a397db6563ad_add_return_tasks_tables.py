"""add return tasks tables

Revision ID: a397db6563ad
Revises: a198e23eef2d
Create Date: 2025-11-29 18:11:46.626880
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a397db6563ad'
down_revision: Union[str, Sequence[str], None] = 'a198e23eef2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create return_tasks + return_task_lines."""
    # --- return_tasks ---
    op.create_table(
        "return_tasks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("po_id", sa.Integer(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_index("ix_return_tasks_po_id", "return_tasks", ["po_id"])
    op.create_index("ix_return_tasks_supplier_id", "return_tasks", ["supplier_id"])
    op.create_index("ix_return_tasks_warehouse_id", "return_tasks", ["warehouse_id"])

    # --- return_task_lines ---
    op.create_table(
        "return_task_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("return_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("po_line_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=True),
        sa.Column("batch_code", sa.String(length=64), nullable=True),
        sa.Column("expected_qty", sa.Integer(), nullable=True),
        sa.Column("picked_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("committed_qty", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("remark", sa.String(length=255), nullable=True),
    )

    op.create_index("ix_return_task_lines_task_id", "return_task_lines", ["task_id"])
    op.create_index("ix_return_task_lines_po_line_id", "return_task_lines", ["po_line_id"])
    op.create_index("ix_return_task_lines_item_id", "return_task_lines", ["item_id"])


def downgrade() -> None:
    """Downgrade schema: drop return_tasks + return_task_lines."""
    op.drop_index("ix_return_task_lines_item_id", table_name="return_task_lines")
    op.drop_index("ix_return_task_lines_po_line_id", table_name="return_task_lines")
    op.drop_index("ix_return_task_lines_task_id", table_name="return_task_lines")
    op.drop_table("return_task_lines")

    op.drop_index("ix_return_tasks_warehouse_id", table_name="return_tasks")
    op.drop_index("ix_return_tasks_supplier_id", table_name="return_tasks")
    op.drop_index("ix_return_tasks_po_id", table_name="return_tasks")
    op.drop_table("return_tasks")
