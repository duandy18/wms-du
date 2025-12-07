"""extend receive_task_lines to include po snapshot

Revision ID: d406745e34a3
Revises: 31c45f47cf0a
Create Date: 2025-12-02 14:42:02.485141
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd406745e34a3'
down_revision: Union[str, Sequence[str], None] = '31c45f47cf0a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 采购行快照字段 ----------
    op.add_column("receive_task_lines", sa.Column("item_sku", sa.String(64)))
    op.add_column("receive_task_lines", sa.Column("category", sa.String(64)))
    op.add_column("receive_task_lines", sa.Column("spec_text", sa.String(255)))
    op.add_column("receive_task_lines", sa.Column("base_uom", sa.String(32)))
    op.add_column("receive_task_lines", sa.Column("purchase_uom", sa.String(32)))
    op.add_column("receive_task_lines", sa.Column("units_per_case", sa.Integer()))

    # ---------- 批次日期 ----------
    op.add_column("receive_task_lines", sa.Column("production_date", sa.Date()))
    op.add_column("receive_task_lines", sa.Column("expiry_date", sa.Date()))


def downgrade() -> None:
    op.drop_column("receive_task_lines", "expiry_date")
    op.drop_column("receive_task_lines", "production_date")

    op.drop_column("receive_task_lines", "units_per_case")
    op.drop_column("receive_task_lines", "purchase_uom")
    op.drop_column("receive_task_lines", "base_uom")
    op.drop_column("receive_task_lines", "spec_text")
    op.drop_column("receive_task_lines", "category")
    op.drop_column("receive_task_lines", "item_sku")
