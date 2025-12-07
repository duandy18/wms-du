"""phase36: drop location_id column from reservations (Soft Reserve cleanup)

Revision ID: p36_20251112_drop_location_from_reservations
Revises: p35_20251112_soft_reserve
Create Date: 2025-11-12 21:00:00.000000
"""
from alembic import op
import sqlalchemy as sa  # noqa: F401

revision = "p36_20251112_drop_location_from_reservations"
down_revision = "p35_20251112_soft_reserve"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
      -- 删除依赖 location_id 的旧索引（若存在）
      IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='public' AND indexname='ix_reservations_item_loc_active'
      ) THEN
        DROP INDEX ix_reservations_item_loc_active;
      END IF;

      IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='public' AND indexname='uq_reserve_idem'
      ) THEN
        DROP INDEX uq_reserve_idem;
      END IF;

      -- 删除列本体（若存在）
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='location_id'
      ) THEN
        ALTER TABLE reservations DROP COLUMN location_id;
      END IF;
    END$$;
    """)


def downgrade() -> None:
    # 回滚时恢复 location_id（允许 NULL），不重建旧索引（避免误导后续逻辑）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='location_id'
      ) THEN
        ALTER TABLE reservations ADD COLUMN location_id INTEGER NULL;
      END IF;
    END$$;
    """)
