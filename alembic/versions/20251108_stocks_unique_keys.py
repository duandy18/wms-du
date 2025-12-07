# alembic/versions/20251108_stocks_unique_keys.py
from alembic import op

revision = "20251108_stocks_unique_keys"
down_revision = "20251108_reservation_allocations"  # 按你的实际链路改
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    ALTER TABLE stocks
      DROP CONSTRAINT IF EXISTS uq_stocks_item_loc_batch;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_stocks_nobatch
      ON stocks (item_id, location_id)
      WHERE batch_id IS NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_stocks_withbatch
      ON stocks (item_id, location_id, batch_id)
      WHERE batch_id IS NOT NULL;
    DO $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_location') THEN
        ALTER TABLE stocks
          ADD CONSTRAINT fk_stocks_location
          FOREIGN KEY (location_id) REFERENCES locations(id) ON DELETE RESTRICT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_item') THEN
        ALTER TABLE stocks
          ADD CONSTRAINT fk_stocks_item
          FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE RESTRICT;
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stocks_batch') THEN
        ALTER TABLE stocks
          ADD CONSTRAINT fk_stocks_batch
          FOREIGN KEY (batch_id) REFERENCES batches(id) ON DELETE SET NULL;
      END IF;
    END $$;
    CREATE INDEX IF NOT EXISTS ix_stocks_item_loc_batch
      ON stocks (item_id, location_id, batch_id);
    CREATE INDEX IF NOT EXISTS ix_stocks_loc ON stocks(location_id);
    """)


def downgrade():
    op.execute("""
    DROP INDEX IF EXISTS ix_stocks_loc;
    DROP INDEX IF EXISTS ix_stocks_item_loc_batch;
    DROP INDEX IF EXISTS uq_stocks_withbatch;
    DROP INDEX IF EXISTS uq_stocks_nobatch;
    ALTER TABLE stocks
      DROP CONSTRAINT IF EXISTS fk_stocks_batch,
      DROP CONSTRAINT IF EXISTS fk_stocks_item,
      DROP CONSTRAINT IF EXISTS fk_stocks_location;
    """)
