"""add FK stock_ledger.item_id -> items(id)

Revision ID: ef4b22fb17a4
Revises: 80d901c60739
Create Date: 2025-11-10 01:50:35.394723
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ef4b22fb17a4"
down_revision: Union[str, Sequence[str], None] = "80d901c60739"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等创建外键；为兼容历史脏数据，先 NOT VALID 再尝试 VALIDATE
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_item_id'
      ) THEN
        ALTER TABLE stock_ledger
          ADD CONSTRAINT fk_stock_ledger_item_id
          FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE RESTRICT
          NOT VALID;
      END IF;
    END$$;
    """)

    # 尝试校验（如果存在非法数据仅提示，不中断迁移）
    op.execute("""
    DO $$
    BEGIN
      BEGIN
        ALTER TABLE stock_ledger VALIDATE CONSTRAINT fk_stock_ledger_item_id;
      EXCEPTION WHEN others THEN
        RAISE NOTICE 'fk_stock_ledger_item_id remains NOT VALID (data needs cleanup)';
      END;
    END$$;
    """)


def downgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='fk_stock_ledger_item_id'
      ) THEN
        ALTER TABLE stock_ledger DROP CONSTRAINT fk_stock_ledger_item_id;
      END IF;
    END$$;
    """)
