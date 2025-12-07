"""rename stocks unique constraint to uq_stocks_item_loc_batch (compat)

Revision ID: 38d1587990e0
Revises: dd5a36088e9b
Create Date: 2025-11-10 08:53:42.041552
"""
from typing import Sequence, Union
from alembic import op

revision: str = "38d1587990e0"
down_revision: Union[str, Sequence[str], None] = "dd5a36088e9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 若老名已存在则不动；否则将新名改回老名以兼容主程序的 ON CONFLICT
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname='uq_stocks_item_loc_batch'
           AND conrelid='stocks'::regclass
      ) THEN
        RETURN;
      END IF;

      IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname='uq_stocks_item_wh_loc_batch'
           AND conrelid='stocks'::regclass
      ) THEN
        ALTER TABLE stocks
          RENAME CONSTRAINT uq_stocks_item_wh_loc_batch
          TO uq_stocks_item_loc_batch;
      END IF;
    END$$;
    """)


def downgrade() -> None:
    # 回滚：把兼容名改回“含 wh”的命名
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname='uq_stocks_item_loc_batch'
           AND conrelid='stocks'::regclass
      ) THEN
        ALTER TABLE stocks
          RENAME CONSTRAINT uq_stocks_item_loc_batch
          TO uq_stocks_item_wh_loc_batch;
      END IF;
    END$$;
    """)
