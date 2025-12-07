"""stock_ledger UC: make uq_ledger_reason_ref_refline_stock NOT DEFERRABLE

Revision ID: 20251106_fix_ledger_uc_not_deferrable
Revises: 20251106_fix_items_id_and_seed_sku001
Create Date: 2025-11-06 17:40:00+08
"""

from alembic import op

revision = "20251106_fix_ledger_uc_not_deferrable"
down_revision = "20251106_fix_items_id_and_seed_sku001"
branch_labels = None
depends_on = None


def upgrade():
    # 将 deferrable 的 UC 替换为 NOT DEFERRABLE（名称保持不变，代码无需改）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname='public'
          AND t.relname='stock_ledger'
          AND c.conname='uq_ledger_reason_ref_refline_stock'
      ) THEN
        ALTER TABLE public.stock_ledger
          DROP CONSTRAINT uq_ledger_reason_ref_refline_stock;
      END IF;

      -- 以相同名称重建为 NOT DEFERRABLE
      ALTER TABLE public.stock_ledger
        ADD CONSTRAINT uq_ledger_reason_ref_refline_stock
        UNIQUE (stock_id, reason, ref, ref_line) NOT DEFERRABLE;
    END $$;
    """)


def downgrade():
    # 回滚：如果真要回退为 deferrable（一般不需要），示例如下；否则仅删除 UC
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname='public'
          AND t.relname='stock_ledger'
          AND c.conname='uq_ledger_reason_ref_refline_stock'
      ) THEN
        ALTER TABLE public.stock_ledger
          DROP CONSTRAINT uq_ledger_reason_ref_refline_stock;
      END IF;

      -- 可选：改回 DEFERRABLE（如果你真的需要）
      ALTER TABLE public.stock_ledger
        ADD CONSTRAINT uq_ledger_reason_ref_refline_stock
        UNIQUE (stock_id, reason, ref, ref_line) DEFERRABLE INITIALLY IMMEDIATE;
    END $$;
    """)
