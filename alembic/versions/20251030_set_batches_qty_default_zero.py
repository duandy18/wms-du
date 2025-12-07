# alembic/versions/20251030_set_batches_qty_default_zero.py
"""batches.qty: set DEFAULT 0 (idempotent)

让新插入的批次在未显式给 qty 时默认 0，避免 NOT NULL 违反。
并修正历史 NULL 值（若存在）。

Revision ID: 20251030_set_batches_qty_default_zero
Revises: 20251030_add_expire_at_to_batches
Create Date: 2025-10-30
"""

from alembic import op
import sqlalchemy as sa

revision = "20251030_set_batches_qty_default_zero"
down_revision = "20251030_add_expire_at_to_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # 设定默认值
    op.alter_column("batches", "qty", server_default=sa.text("0"))
    # 修正历史 NULL（若有）
    conn.exec_driver_sql("UPDATE batches SET qty=0 WHERE qty IS NULL")


def downgrade() -> None:
    # 仅移除默认值（不改动已有数据）
    op.alter_column("batches", "qty", server_default=None)
