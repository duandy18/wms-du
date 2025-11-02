"""schema additions batch-1 (safe indexes only)

Revision ID: 6869fc360d86
Revises: 6077053642c5
Create Date: 2025-10-29 19:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "6869fc360d86"
down_revision = "6077053642c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— 省略：你当前已通过的索引创建 & 守卫逻辑（保持不变） ——
    # （略）
    pass


def downgrade() -> None:
    conn = op.get_bind()

    # 1) 先安全删除可能存在的唯一约束（如果存在）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
         WHERE t.relname = 'stock_ledger'
           AND c.contype = 'u'
           AND c.conname = 'uq_ledger_reason_ref_refline_stock'
      ) THEN
        EXECUTE 'ALTER TABLE public.stock_ledger DROP CONSTRAINT uq_ledger_reason_ref_refline_stock';
      END IF;
    END$$;
    """))

    # 2) 再删除同名索引（仅当它不是某个约束的 backing index）
    conn.execute(sa.text("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
          FROM pg_class idx
         WHERE idx.relname = 'uq_ledger_reason_ref_refline_stock'
           AND idx.relkind = 'i'
           AND NOT EXISTS (
             SELECT 1
               FROM pg_constraint c
              WHERE c.conindid = idx.oid
           )
      ) THEN
        EXECUTE 'DROP INDEX IF EXISTS public.uq_ledger_reason_ref_refline_stock';
      END IF;
    END$$;
    """))

    # 3) 其余本文件创建过的通用索引，按需幂等删除（仍可保留 IF EXISTS）
    # 示例（如你在 upgrade 里创建过以下索引，可在此删除）：
    # op.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_order_id"))
    # op.execute(sa.text("DROP INDEX IF EXISTS public.ix_items_sku"))
    # ...（保留你已有的其它 DROP INDEX IF EXISTS 语句即可）
