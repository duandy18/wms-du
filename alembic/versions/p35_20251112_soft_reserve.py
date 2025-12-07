"""phase35: soft-reserve enablement on existing schema (no location in logic)

Revision ID: p35_20251112_soft_reserve
Revises: p34_20251112_seed
Create Date: 2025-11-12 18:45:00.000000
"""
from alembic import op

revision = "p35_20251112_soft_reserve"
down_revision = "p34_20251112_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) reservations：补充 Soft Reserve 需要的字段（保留旧列不删）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='platform'
      ) THEN
        ALTER TABLE reservations ADD COLUMN platform TEXT NULL;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='shop_id'
      ) THEN
        ALTER TABLE reservations ADD COLUMN shop_id TEXT NULL;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='warehouse_id'
      ) THEN
        ALTER TABLE reservations ADD COLUMN warehouse_id INTEGER NOT NULL DEFAULT 1;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='updated_at'
      ) THEN
        ALTER TABLE reservations ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservations' AND column_name='expire_at'
      ) THEN
        ALTER TABLE reservations ADD COLUMN expire_at TIMESTAMPTZ NULL;
      END IF;

      BEGIN
        CREATE UNIQUE INDEX uq_reservations_platform_shop_ref
          ON reservations(platform, shop_id, ref)
          WHERE platform IS NOT NULL AND shop_id IS NOT NULL;
      EXCEPTION WHEN duplicate_table THEN NULL;
      WHEN duplicate_object THEN NULL;
      END;
    END$$;
    """)

    # 2) reservation_lines：补充 Soft Reserve 所需字段（consumed_qty/status/updated_at）
    op.execute("""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservation_lines' AND column_name='consumed_qty'
      ) THEN
        ALTER TABLE reservation_lines ADD COLUMN consumed_qty INTEGER NOT NULL DEFAULT 0;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservation_lines' AND column_name='status'
      ) THEN
        ALTER TABLE reservation_lines ADD COLUMN status TEXT NOT NULL DEFAULT 'open';
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='public' AND table_name='reservation_lines' AND column_name='updated_at'
      ) THEN
        ALTER TABLE reservation_lines ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
      END IF;

      -- 清理重复外键（可能存在 fkey 与 fkey1）
      BEGIN
        ALTER TABLE reservation_lines
          DROP CONSTRAINT IF EXISTS reservation_lines_reservation_id_fkey1;
      EXCEPTION WHEN undefined_object THEN
        NULL;
      END;

      -- 确保存在正确外键（若已存在则忽略）
      BEGIN
        ALTER TABLE reservation_lines
          ADD CONSTRAINT reservation_lines_reservation_id_fkey
          FOREIGN KEY (reservation_id) REFERENCES reservations(id) ON DELETE CASCADE;
      EXCEPTION WHEN duplicate_object THEN
        NULL;
      END;

      -- 队列索引（item/status/时间）
      BEGIN
        CREATE INDEX ix_reserve_line_item_queue
          ON reservation_lines (item_id, status, created_at);
      EXCEPTION WHEN duplicate_table THEN
        NULL;
      WHEN duplicate_object THEN
        NULL;
      END;
    END$$;
    """)

    # 3) v_available：保持旧视图列顺序与类型（qty 为 integer）
    op.execute("""
    CREATE OR REPLACE VIEW v_available (item_id, batch_code, warehouse_id, qty) AS
    SELECT
        s.item_id,
        s.batch_code,
        s.warehouse_id,
        -- cast 为 integer，防止 bigint 类型不匹配
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
    # 降级不删除新增列，避免历史数据丢失
    op.execute("DROP VIEW IF EXISTS v_available;")
    op.execute("DROP INDEX IF EXISTS ix_reserve_line_item_queue;")
    op.execute("DROP INDEX IF EXISTS uq_reservations_platform_shop_ref;")
