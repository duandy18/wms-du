"""ensure stock_snapshots has column snapshot_date (compat rename/add)

Revision ID: 20251015_fix_stock_snapshots_snapshot_date
Revises: 20251015_items_id_identity
Create Date: 2025-10-15
"""
from alembic import op

revision = "20251015_fix_stock_snapshots_snapshot_date"
down_revision = "20251015_items_id_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
          has_table boolean;
          has_snapshot_date boolean;
          has_snap_date boolean;
          has_date boolean;
        BEGIN
          has_table := to_regclass('public.stock_snapshots') IS NOT NULL;

          IF has_table THEN
            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='stock_snapshots'
                AND column_name='snapshot_date'
            ) INTO has_snapshot_date;

            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='stock_snapshots'
                AND column_name='snap_date'
            ) INTO has_snap_date;

            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='stock_snapshots'
                AND column_name='date'
            ) INTO has_date;

            IF NOT has_snapshot_date THEN
              IF has_snap_date THEN
                ALTER TABLE public.stock_snapshots
                  RENAME COLUMN snap_date TO snapshot_date;
              ELSIF has_date THEN
                ALTER TABLE public.stock_snapshots
                  RENAME COLUMN date TO snapshot_date;
              ELSE
                ALTER TABLE public.stock_snapshots
                  ADD COLUMN snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE;
                ALTER TABLE public.stock_snapshots
                  ALTER COLUMN snapshot_date DROP DEFAULT;
              END IF;
            END IF;
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    pass
