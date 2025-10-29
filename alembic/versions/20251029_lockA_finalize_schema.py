from alembic import op
import sqlalchemy as sa

revision = "20251029_lockA_finalize_schema"
down_revision = "63af7f94ad50"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ========= 0) 预检查：locations.warehouse_id 必须存在 =========
    conn.exec_driver_sql("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='locations' AND column_name='warehouse_id'
          ) THEN
            RAISE EXCEPTION 'locations.warehouse_id is required by Lock-A migration.';
          END IF;
        END $$;
    """)

    # ========= 1) stocks.warehouse_id：ADD IF NOT EXISTS → 回填 → NOT NULL → 外键 =========
    op.execute("ALTER TABLE stocks ADD COLUMN IF NOT EXISTS warehouse_id INTEGER")

    # 从 locations 回填（幂等：仅 NULL 时更新）
    conn.exec_driver_sql("""
        UPDATE stocks s
           SET warehouse_id = l.warehouse_id
          FROM locations l
         WHERE l.id = s.location_id
           AND s.warehouse_id IS NULL;
    """)

    # MAIN 仓兜底（幂等）
    conn.exec_driver_sql("""
        INSERT INTO warehouses (name)
        SELECT 'MAIN'
        WHERE NOT EXISTS (SELECT 1 FROM warehouses WHERE name='MAIN');

        WITH mainw AS (SELECT id FROM warehouses WHERE name='MAIN' LIMIT 1)
        UPDATE stocks s
           SET warehouse_id = (SELECT id FROM mainw)
         WHERE s.warehouse_id IS NULL;
    """)

    # 设为 NOT NULL（幂等）
    op.execute("ALTER TABLE stocks ALTER COLUMN warehouse_id SET NOT NULL")

    # 外键（若不存在则创建；DEFERRABLE）
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema='public' AND table_name='stocks' AND constraint_name='fk_stocks_warehouse'
          ) THEN
            ALTER TABLE stocks
              ADD CONSTRAINT fk_stocks_warehouse
              FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
              DEFERRABLE INITIALLY DEFERRED;
          END IF;
        END $$;
    """)

    # ========= 2) batches.qty 收紧为 NOT NULL（先清 NULL） =========
    conn.exec_driver_sql("UPDATE batches SET qty = 0 WHERE qty IS NULL;")
    # 如果已经是 NOT NULL，这句也安全
    op.execute("ALTER TABLE batches ALTER COLUMN qty SET NOT NULL")

    # ========= 3) stocks.batch_code：ADD IF NOT EXISTS → 回填 → 合成批次 → DROP DEFAULT =========
    # 若不存在则加列（带临时默认值，便于回填）
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='stocks' AND column_name='batch_code'
          ) THEN
            ALTER TABLE stocks
              ADD COLUMN batch_code VARCHAR(64) NOT NULL DEFAULT 'MIG-UNSPEC';
          END IF;
        END $$;
    """)

    # “一地一批” → 用真批次码回填（幂等）
    conn.exec_driver_sql("""
        WITH one AS (
          SELECT item_id, warehouse_id, location_id, MIN(batch_code) AS batch_code
            FROM batches
           GROUP BY item_id, warehouse_id, location_id
          HAVING COUNT(*) = 1
        )
        UPDATE stocks s
           SET batch_code = o.batch_code
          FROM one o
         WHERE s.item_id = o.item_id
           AND s.warehouse_id = o.warehouse_id
           AND s.location_id = o.location_id
           AND s.batch_code = 'MIG-UNSPEC';
    """)

    # 为剩余未回填的 stocks 生成“合成批次”（幂等；batches 有唯一索引兜底）
    conn.exec_driver_sql("""
        INSERT INTO batches (item_id, warehouse_id, location_id, batch_code, expiry_date, qty)
        SELECT s.item_id,
               s.warehouse_id,
               s.location_id,
               CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id),
               NULL::date,
               0
          FROM stocks s
     LEFT JOIN batches b
            ON b.item_id = s.item_id
           AND b.warehouse_id = s.warehouse_id
           AND b.location_id = s.location_id
           AND b.batch_code = CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id)
         WHERE s.batch_code = 'MIG-UNSPEC'
           AND b.item_id IS NULL
        ON CONFLICT DO NOTHING;
    """)

    # 将剩余 MIG-UNSPEC 回填为合成批次码（幂等）
    conn.exec_driver_sql("""
        UPDATE stocks s
           SET batch_code = CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id)
         WHERE s.batch_code = 'MIG-UNSPEC';
    """)

    # 确保 NOT NULL（即便列原来存在为可空，也会被设为非空）
    op.execute("ALTER TABLE stocks ALTER COLUMN batch_code SET NOT NULL")

    # 为规避 pending trigger events，单独事务块里 DROP DEFAULT（若存在）
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute("""
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='stocks' AND column_name='batch_code' AND column_default IS NOT NULL
              ) THEN
                ALTER TABLE stocks ALTER COLUMN batch_code DROP DEFAULT;
              END IF;
            END $$;
        """)

    # ========= 4) 约束与索引：删旧 UQ → 建索引 → 唯一约束（USING INDEX） =========
    # 删除旧 loc-only UQ（若存在）
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_location")

    # batches UQ 索引（若不存在则创建）
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_batches_item_wh_loc_code
          ON batches (item_id, warehouse_id, location_id, batch_code)
    """)

    # stocks 非唯一查询索引
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_stocks_item_wh_loc_batch
          ON stocks (item_id, warehouse_id, location_id, batch_code)
    """)

    # 先建唯一索引（若不存在）
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_class WHERE relkind='i' AND relname='uq_stocks_item_wh_loc_code_idx'
          ) THEN
            CREATE UNIQUE INDEX uq_stocks_item_wh_loc_code_idx
              ON stocks (item_id, warehouse_id, location_id, batch_code);
          END IF;
        END $$;
    """)

    # 再用 USING INDEX 绑定唯一约束（若不存在）
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='uq_stocks_item_wh_loc_code'
          ) THEN
            ALTER TABLE stocks
              ADD CONSTRAINT uq_stocks_item_wh_loc_code
              UNIQUE USING INDEX uq_stocks_item_wh_loc_code_idx;
          END IF;
        END $$;
    """)


def downgrade():
    # 回滚顺序：约束/索引 → 列
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_wh_loc_code")
    op.execute("DROP INDEX IF EXISTS uq_stocks_item_wh_loc_code_idx")
    op.execute("DROP INDEX IF EXISTS idx_stocks_item_wh_loc_batch")
    op.execute("DROP INDEX IF EXISTS uq_batches_item_wh_loc_code")
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS fk_stocks_warehouse")

    op.execute("ALTER TABLE batches ALTER COLUMN qty DROP NOT NULL")

    op.execute("ALTER TABLE stocks ALTER COLUMN batch_code DROP NOT NULL")
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS batch_code")

    op.execute("ALTER TABLE stocks ALTER COLUMN warehouse_id DROP NOT NULL")
    op.execute("ALTER TABLE stocks DROP COLUMN IF EXISTS warehouse_id")
