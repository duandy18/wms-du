"""add uniq constraint on stock_ledger (stock_id,reason,ref,ref_line)

Revision ID: 567351fff27e
Revises: 8b3d2b0f7e21
Create Date: 2025-11-10 01:15:38.023334
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "567351fff27e"
down_revision: str | None = "8b3d2b0f7e21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 幂等创建唯一约束：
    #    - 若同名约束已存在：跳过
    #    - 若同名索引已存在：附着为约束（USING INDEX）
    #    - 否则：直接 ADD CONSTRAINT UNIQUE (...)
    op.execute("""
    DO $$
    DECLARE
      idx_oid oid;
    BEGIN
      -- 已有同名约束：直接返回
      IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='uq_ledger_reason_ref_refline_stock'
      ) THEN
        RETURN;
      END IF;

      -- 是否已有同名索引（任何类型）
      SELECT c.oid
        INTO idx_oid
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
       WHERE c.relname = 'uq_ledger_reason_ref_refline_stock'
         AND n.nspname = current_schema();

      IF idx_oid IS NOT NULL THEN
        -- 将该索引附着为唯一约束（若索引非 UNIQUE 会报错，需要先人工处理）
        EXECUTE 'ALTER TABLE stock_ledger
                   ADD CONSTRAINT uq_ledger_reason_ref_refline_stock
                   UNIQUE USING INDEX uq_ledger_reason_ref_refline_stock';
      ELSE
        -- 正常创建唯一约束
        EXECUTE 'ALTER TABLE stock_ledger
                   ADD CONSTRAINT uq_ledger_reason_ref_refline_stock
                   UNIQUE (stock_id, reason, ref, ref_line)';
      END IF;
    END$$;
    """)

    # 2) 可选：补充常用索引（若未存在）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='idx_stock_ledger_stock_id' AND n.nspname=current_schema()
      ) THEN
        CREATE INDEX idx_stock_ledger_stock_id ON stock_ledger(stock_id);
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE c.relname='idx_stock_ledger_occurred_at' AND n.nspname=current_schema()
      ) THEN
        CREATE INDEX idx_stock_ledger_occurred_at ON stock_ledger(occurred_at);
      END IF;
    END$$;
    """)


def downgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname='uq_ledger_reason_ref_refline_stock'
      ) THEN
        ALTER TABLE stock_ledger DROP CONSTRAINT uq_ledger_reason_ref_refline_stock;
      END IF;
    END$$;
    """)
    op.execute("DROP INDEX IF EXISTS idx_stock_ledger_stock_id;")
    op.execute("DROP INDEX IF EXISTS idx_stock_ledger_occurred_at;")
