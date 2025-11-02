"""fix snapshot unique key to (snapshot_date, item_id, location_id)

Revision ID: 20251031_fix_snapshot_unique_by_item_loc
Revises: 20251031_event_error_log_drop_legacy_columns
Create Date: 2025-10-31
"""
from alembic import op
import sqlalchemy as sa

revision = "20251031_fix_snapshot_unique_by_item_loc"
down_revision = "20251031_event_error_log_drop_legacy_columns"
branch_labels = None
depends_on = None

def upgrade():
    # 1) drop legacy wide unique (day + item)
    op.execute("ALTER TABLE stock_snapshots DROP CONSTRAINT IF EXISTS uq_stock_snapshots_day_item;")
    # 2) ensure (day + item + location) unique exists
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_stock_snapshots_cut_item_loc'
      ) THEN
        ALTER TABLE stock_snapshots
          ADD CONSTRAINT uq_stock_snapshots_cut_item_loc
          UNIQUE (snapshot_date, item_id, location_id);
      END IF;
    END $$;
    """)

def downgrade():
    # best-effort: restore legacy unique (day + item), drop the new one
    op.execute("ALTER TABLE stock_snapshots DROP CONSTRAINT IF EXISTS uq_stock_snapshots_cut_item_loc;")
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_stock_snapshots_day_item'
      ) THEN
        ALTER TABLE stock_snapshots
          ADD CONSTRAINT uq_stock_snapshots_day_item
          UNIQUE (snapshot_date, item_id);
      END IF;
    END $$;
    """)
