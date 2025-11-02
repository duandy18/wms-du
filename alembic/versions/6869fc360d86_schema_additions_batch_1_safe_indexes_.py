"""schema additions batch-1 (safe indexes only, CI-safe downgrade)

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
    # 本文件的 upgrade 留空或保持你已有“新增索引/轻量变更”的内容。
    # 这里留空即可（此前引发 CI 回滚错误的是 downgrade 阶段对索引/约束的删除顺序）。
    pass


def downgrade() -> None:
    """CI 回滚期望：先删 '唯一约束'，再删其背后的索引；其它普通索引直接 IF EXISTS 删除。"""
    conn = op.get_bind()

    # 1) 若 stock_ledger 上存在 UQ 约束，则先删除约束
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

    # 2) 再删除同名索引（确保它不是某个约束的 backing index）
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

    # 3) 若你在 upgrade() 里创建过其它普通索引，也可在此用 IF EXISTS 幂等删除
    # 示例（按需启用）：
    # conn.execute(sa.text("DROP INDEX IF EXISTS public.ix_order_items_order_id"))
    # conn.execute(sa.text("DROP INDEX IF EXISTS public.ix_items_sku"))
