"""phase37: soft-reserve cleanup - drop location_id & legacy indexes, fix fkeys

Revision ID: p37_20251112_soft_reserve_cleanup_drop_location
Revises: p36_20251112_drop_location_from_reservations
Create Date: 2025-11-12 21:30:00.000000
"""
from alembic import op

revision = "p37_20251112_soft_reserve_cleanup_drop_location"
down_revision = "p36_20251112_drop_location_from_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) reservations: 删除依赖 location_id 的遗留索引；再删列 location_id（若仍存在）
    op.execute("""
    DO $$
    BEGIN
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

      IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='location_id'
      ) THEN
        ALTER TABLE reservations DROP COLUMN location_id;
      END IF;
    END$$;
    """)

    # 2) reservation_lines: 删除重复外键 fkey1（保留标准名的 fkey）
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema='public'
          AND table_name='reservation_lines'
          AND constraint_name='reservation_lines_reservation_id_fkey1'
      ) THEN
        ALTER TABLE reservation_lines
          DROP CONSTRAINT reservation_lines_reservation_id_fkey1;
      END IF;
    END$$;
    """)

    # 3) reservations: 补上幂等唯一索引（platform, shop_id, ref）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='public' AND indexname='uq_reservations_platform_shop_ref'
      ) THEN
        CREATE UNIQUE INDEX uq_reservations_platform_shop_ref
          ON reservations(platform, shop_id, ref);
      END IF;
    END$$;
    """)

    # 4) v_available：保持旧列顺序与列名（最后一列仍为 qty，且强制 integer）
    op.execute("""
    CREATE OR REPLACE VIEW v_available (item_id, batch_code, warehouse_id, qty) AS
    SELECT
        s.item_id,
        s.batch_code,
        s.warehouse_id,
        (s.qty - COALESCE((
            SELECT (SUM(rl.qty - rl.consumed_qty))::integer
            FROM reservation_lines rl
            JOIN reservations r ON r.id = rl.reservation_id
            WHERE rl.item_id = s.item_id
              AND r.warehouse_id = s.warehouse_id
              AND r.status IN ('open', 'PLANNED', 'ACTIVE')
        ), 0))::integer AS qty
    FROM stocks s;
    """)


def downgrade() -> None:
    # 回滚：恢复列与索引的“壳”，不恢复旧语义
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='location_id'
      ) THEN
        ALTER TABLE reservations ADD COLUMN location_id INTEGER NULL;
      END IF;

      IF EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='public' AND indexname='uq_reservations_platform_shop_ref'
      ) THEN
        DROP INDEX uq_reservations_platform_shop_ref;
      END IF;
    END$$;
    """)
