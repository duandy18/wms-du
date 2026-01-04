"""drop old FK stock_ledger.stock_id -> stocks(id) (fk_stock_ledger_stock_id_stocks)

Revision ID: 8ccea664a61e
Revises: ef4b22fb17a4
Create Date: 2025-11-10 02:08:45.800599
"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ccea664a61e"
down_revision: Union[str, Sequence[str], None] = "ef4b22fb17a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等删除旧外键（仅当存在时）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
          FROM pg_constraint c
         WHERE c.conname = 'fk_stock_ledger_stock_id_stocks'
      ) THEN
        ALTER TABLE stock_ledger
          DROP CONSTRAINT fk_stock_ledger_stock_id_stocks;
      END IF;
    END$$;
    """)


def downgrade() -> None:
    # 回滚：按旧行为重建（ON UPDATE CASCADE ON DELETE RESTRICT），幂等
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
         WHERE c.conname = 'fk_stock_ledger_stock_id_stocks'
      ) THEN
        ALTER TABLE stock_ledger
          ADD CONSTRAINT fk_stock_ledger_stock_id_stocks
          FOREIGN KEY (stock_id) REFERENCES stocks(id)
          ON UPDATE CASCADE ON DELETE RESTRICT;
      END IF;
    END$$;
    """)
