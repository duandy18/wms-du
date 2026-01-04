"""cleanup old batches unique constraint (drop uq_batches_item_code)

Revision ID: 20251112_batches_constraint_cleanup
Revises: 20251112_add_warehouse_id_to_batches
Create Date: 2025-11-12 14:20:00
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op

revision: str = "20251112_batches_constraint_cleanup"
down_revision: Union[str, Sequence[str], None] = "20251112_add_warehouse_id_to_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 仅删除旧唯一约束（如果存在）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='batches'::regclass
          AND contype='u'
          AND conname='uq_batches_item_code'
      ) THEN
        ALTER TABLE batches DROP CONSTRAINT uq_batches_item_code;
      END IF;
    END $$;
    """)


def downgrade() -> None:
    # 可选：回放旧唯一约束（多数场景不需要，提供以满足可逆性）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='batches'::regclass
          AND contype='u'
          AND conname='uq_batches_item_code'
      ) THEN
        ALTER TABLE batches
          ADD CONSTRAINT uq_batches_item_code UNIQUE (item_id, batch_code);
      END IF;
    END $$;
    """)
