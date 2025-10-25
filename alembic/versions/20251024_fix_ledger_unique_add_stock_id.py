"""widen stock_ledger unique key to include stock_id (idempotent)

Revision ID: 20251024_fix_ledger_unique_add_stock_id
Revises: 20251023_event_store
Create Date: 2025-10-24 10:45:00
"""
from __future__ import annotations

from alembic import op

# 如果你的上一条 revision 不是这个，请按实际 heads 替换
revision = "20251024_fix_ledger_unique_add_stock_id"
down_revision = "20251023_event_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) 幂等删除旧的三列唯一约束（不同历史名都尝试）
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_stock_ledger_reason_ref_ref_line'
              AND conrelid = 'public.stock_ledger'::regclass
          ) THEN
            ALTER TABLE public.stock_ledger
              DROP CONSTRAINT uq_stock_ledger_reason_ref_ref_line;
          END IF;

          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_stock_ledger_reason_ref_refline'
              AND conrelid = 'public.stock_ledger'::regclass
          ) THEN
            ALTER TABLE public.stock_ledger
              DROP CONSTRAINT uq_stock_ledger_reason_ref_refline;
          END IF;

          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'e4b9177afe8d_putaway_add_uniq_reason_ref_ref_line_'
              AND conrelid = 'public.stock_ledger'::regclass
          ) THEN
            ALTER TABLE public.stock_ledger
              DROP CONSTRAINT e4b9177afe8d_putaway_add_uniq_reason_ref_ref_line_;
          END IF;
        END
        $$;
        """
    )

    # 2) 如果已经存在等价的四列唯一约束（不论名字），则直接跳过后续创建
    op.execute(
        """
        DO $$
        DECLARE
          t_oid oid;
          col_reason smallint;
          col_ref smallint;
          col_ref_line smallint;
          col_stock_id smallint;
          cols_needed smallint[];
          exists_same boolean;
        BEGIN
          SELECT 'public.stock_ledger'::regclass INTO t_oid;
          SELECT attnum INTO col_reason   FROM pg_attribute WHERE attrelid=t_oid AND attname='reason'   AND NOT attisdropped;
          SELECT attnum INTO col_ref      FROM pg_attribute WHERE attrelid=t_oid AND attname='ref'      AND NOT attisdropped;
          SELECT attnum INTO col_ref_line FROM pg_attribute WHERE attrelid=t_oid AND attname='ref_line' AND NOT attisdropped;
          SELECT attnum INTO col_stock_id FROM pg_attribute WHERE attrelid=t_oid AND attname='stock_id' AND NOT attisdropped;

          cols_needed := ARRAY[col_reason, col_ref, col_ref_line, col_stock_id]::smallint[];

          SELECT EXISTS (
            SELECT 1
            FROM pg_constraint c
            WHERE c.conrelid = t_oid
              AND c.contype = 'u'
              AND c.conkey IS NOT NULL
              AND array_length(c.conkey,1) = 4
              AND (SELECT array_agg(x ORDER BY x) FROM unnest(c.conkey) x)
                  = (SELECT array_agg(y ORDER BY y) FROM unnest(cols_needed) y)
          ) INTO exists_same;

          IF exists_same THEN
            -- 已存在等价唯一约束，直接返回
            RETURN;
          END IF;

          -- 若存在同名索引，先删除（可能有人手工建过重名索引，阻塞约束创建）
          IF EXISTS (
            SELECT 1 FROM pg_class i
            JOIN pg_namespace n ON n.oid = i.relnamespace
            WHERE i.relname = 'uq_ledger_reason_ref_refline_stock'
              AND n.nspname = 'public'
              AND i.relkind IN ('i','I')
          ) THEN
            DROP INDEX public.uq_ledger_reason_ref_refline_stock;
          END IF;

          -- 如不存在同名唯一约束，则创建
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_ledger_reason_ref_refline_stock'
              AND conrelid = t_oid
          ) THEN
            ALTER TABLE public.stock_ledger
              ADD CONSTRAINT uq_ledger_reason_ref_refline_stock
              UNIQUE (reason, ref, ref_line, stock_id);
          END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # 1) 删除四列唯一约束（若存在）
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_ledger_reason_ref_refline_stock'
              AND conrelid = 'public.stock_ledger'::regclass
          ) THEN
            ALTER TABLE public.stock_ledger
              DROP CONSTRAINT uq_ledger_reason_ref_refline_stock;
          END IF;
        END
        $$;
        """
    )

    # 2) 还原三列唯一约束（若不存在）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_stock_ledger_reason_ref_ref_line'
              AND conrelid = 'public.stock_ledger'::regclass
          ) THEN
            ALTER TABLE public.stock_ledger
              ADD CONSTRAINT uq_stock_ledger_reason_ref_ref_line
              UNIQUE (reason, ref, ref_line);
          END IF;
        END
        $$;
        """
    )
