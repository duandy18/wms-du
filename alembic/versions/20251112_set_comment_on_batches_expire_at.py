"""set comment on batches.expire_at to match model

Revision ID: 20251112_set_comment_on_batches_expire_at
Revises: 20251112_batches_constraint_cleanup  # ← 改成你当前 head
Create Date: 2025-11-12 14:35:00
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "20251112_set_comment_on_batches_expire_at"
down_revision: Union[str, Sequence[str], None] = "20251112_batches_constraint_cleanup"  # ← 同上
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 与模型对齐列注释
    op.execute("COMMENT ON COLUMN batches.expire_at IS '到期日（FEFO）'")


def downgrade() -> None:
    # 回滚时移除注释
    op.execute("COMMENT ON COLUMN batches.expire_at IS NULL")
