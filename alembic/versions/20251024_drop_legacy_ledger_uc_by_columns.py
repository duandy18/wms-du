"""drop legacy 3-col UC on stock_ledger; ensure 4-col UC exists (idempotent)

Revision ID: 20251024_drop_legacy_ledger_uc_by_columns
Revises: 20251024_fix_ledger_unique_add_stock_id
Create Date: 2025-10-24 11:20:00
"""
from __future__ import annotations

from alembic import op

# Adjust down_revision to your actual previous revision if different
revision = "20251024_drop_legacy_ledger_uc_by_columns"
down_revision = "20251024_fix_ledger_unique_add_stock_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Drop ANY legacy 3-column (reason, ref, ref_line) unique constraint on stock_ledger.
    #    We match by column set via pg_constraint.conkey, so names do not matter.
    op.execute(
        """
        DO $$
        DECLARE
          t_oid oid := 'public.stock_ledger'::regclass;
          a_reason   smallint;
          a_ref      smallint;
          a_ref_line smallint;
          cols3      smallint[];
          r record;
        BEGIN
          SELECT attnum INTO a_reason    FROM pg_attribute WHERE attrelid=t_oid AND attname='reason'   AND NOT attisdropped;
          SELECT attnum INTO a_ref       FROM pg_attribute WHERE attrelid=t_oid AND attname='ref'      AND NOT attisdropped;
          SELECT attnum INTO a_ref_line  FROM pg_attribute WHERE attrelid=t_oid AND attname='ref_line' AND NOT attisdropped;

          cols3 := ARRAY[a_reason, a_ref, a_ref_line]::smallint[];

          FOR r IN
            SELECT conname
            FROM pg_constraint c
            WHERE c.conrelid = t_oid
              AND c.contype = 'u'
              AND c.conkey IS NOT NULL
              AND array_length(c.conkey,1) = 3
              AND (SELECT array_agg(x ORDER BY x) FROM unnest(c.conkey) x)
                  = (SELECT array_agg(y ORDER BY y) FROM unnest(cols3) y)
          LOOP
            EXECUTE format('ALTER TABLE public.stock_ledger DROP CONSTRAINT %I', r.conname);
          END LOOP;
        END
        $$;
        """
    )

    # 2) Ensure a 4-column UC (reason, ref, ref_line, stock_id) exists.
    #    If an equivalent UC (same column set) already exists (any name), do nothing.
    #    If a same-named index/UC blocks creation, drop it first, then create UC with standard name.
    op.execute(
        """
        DO $$
        DECLARE
          t_oid oid := 'public.stock_ledger'::regclass;
          a_reason   smallint;
          a_ref      smallint;
          a_ref_line smallint;
          a_stock_id smallint;
          cols4      smallint[];
          exists_same boolean;
        BEGIN
          SELECT attnum INTO a_reason    FROM pg_attribute WHERE attrelid=t_oid AND attname='reason'   AND NOT attisdropped;
          SELECT attnum INTO a_ref       FROM pg_attribute WHERE attrelid=t_oid AND attname='ref'      AND NOT attisdropped;
          SELECT attnum INTO a_ref_line  FROM pg_attribute WHERE attrelid=t_oid AND attname='ref_line' AND NOT attisdropped;
          SELECT attnum INTO a_stock_id  FROM pg_attribute WHERE attrelid=t_oid AND attname='stock_id' AND NOT attisdropped;

          cols4 := ARRAY[a_reason, a_ref, a_ref_line, a_stock_id]::smallint[];

          SELECT EXISTS (
            SELECT 1
            FROM pg_constraint c
            WHERE c.conrelid = t_oid
              AND c.contype = 'u'
              AND c.conkey IS NOT NULL
              AND array_length(c.conkey,1) = 4
              AND (SELECT array_agg(x ORDER BY x) FROM unnest(c.conkey) x)
                  = (SELECT array_agg(y ORDER BY y) FROM unnest(cols4) y)
          ) INTO exists_same;

          IF exists_same THEN
            RETURN; -- Equivalent unique constraint already exists
          END IF;

          -- Drop same-named index if exists (may block adding the constraint)
          IF EXISTS (
            SELECT 1 FROM pg_class i
            JOIN pg_namespace n ON n.oid = i.relnamespace
            WHERE i.relname = 'uq_ledger_reason_ref_refline_stock'
              AND n.nspname = 'public'
              AND i.relkind IN ('i','I')
          ) THEN
            DROP INDEX public.uq_ledger_reason_ref_refline_stock;
          END IF;

          -- Drop same-named constraint if exists (just to normalize to the standard name)
          IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname='uq_ledger_reason_ref_refline_stock'
              AND conrelid = t_oid
          ) THEN
            ALTER TABLE public.stock_ledger
              DROP CONSTRAINT uq_ledger_reason_ref_refline_stock;
          END IF;

          ALTER TABLE public.stock_ledger
            ADD CONSTRAINT uq_ledger_reason_ref_refline_stock
            UNIQUE (reason, ref, ref_line, stock_id);
        END
        $$;
        """
    )


def downgrade() -> None:
    # Idempotent rollback: drop 4-col UC; re-create 3-col UC only if missing.
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
