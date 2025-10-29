from alembic import op
import sqlalchemy as sa

revision = "20251029_lockA_finalize_schema"
down_revision = "63af7f94ad50"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ========= 0) 预检查（强制存在前置表/列） =========
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

    # ========= 1) stocks.warehouse_id：新增 → 回填 → NOT NULL → 外键 =========
    op.add_column("stocks", sa.Column("warehouse_id", sa.Integer(), nullable=True))

    conn.exec_driver_sql("""
        UPDATE stocks s
           SET warehouse_id = l.warehouse_id
          FROM locations l
         WHERE l.id = s.location_id
           AND s.warehouse_id IS NULL;
    """)

    conn.exec_driver_sql("""
        INSERT INTO warehouses (name)
        SELECT 'MAIN'
        WHERE NOT EXISTS (SELECT 1 FROM warehouses WHERE name='MAIN');

        WITH mainw AS (SELECT id FROM warehouses WHERE name='MAIN' LIMIT 1)
        UPDATE stocks s
           SET warehouse_id = (SELECT id FROM mainw)
         WHERE s.warehouse_id IS NULL;
    """)

    op.alter_column("stocks", "warehouse_id", nullable=False)

    op.execute("""
        ALTER TABLE stocks
        ADD CONSTRAINT fk_stocks_warehouse
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
        DEFERRABLE INITIALLY DEFERRED
    """)

    # ========= 2) batches.qty 收紧为 NOT NULL =========
    conn.exec_driver_sql("UPDATE batches SET qty = 0 WHERE qty IS NULL;")
    op.alter_column("batches", "qty", existing_type=sa.Integer(), nullable=False)

    # ========= 3) stocks.batch_code：新增 → 回填 → 合成批次 → 去默认 =========
    op.add_column(
        "stocks",
        sa.Column("batch_code", sa.String(length=64), nullable=False, server_default="MIG-UNSPEC"),
    )

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

    conn.exec_driver_sql("""
        UPDATE stocks s
           SET batch_code = CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id)
         WHERE s.batch_code = 'MIG-UNSPEC';
    """)

    # 修复：在单独 autocommit 块中 DROP DEFAULT，避免 pending trigger events
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute("ALTER TABLE stocks ALTER COLUMN batch_code DROP DEFAULT")

    # ========= 4) 约束与索引：删旧 UQ → 建索引 → 新 UQ =========
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_location")

    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_batches_item_wh_loc_code
          ON batches (item_id, warehouse_id, location_id, batch_code)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_stocks_item_wh_loc_batch
          ON stocks (item_id, warehouse_id, location_id, batch_code)
    """)

    op.execute("""
        ALTER TABLE stocks
          ADD CONSTRAINT uq_stocks_item_wh_loc_code
          UNIQUE (item_id, warehouse_id, location_id, batch_code) NOT VALID
    """)


def downgrade():
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_wh_loc_code")
    op.execute("DROP INDEX IF EXISTS idx_stocks_item_wh_loc_batch")
    op.execute("DROP INDEX IF EXISTS uq_batches_item_wh_loc_code")
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS fk_stocks_warehouse")

    op.alter_column("batches", "qty", existing_type=sa.Integer(), nullable=True)

    op.drop_column("stocks", "batch_code")
    op.alter_column("stocks", "warehouse_id", nullable=True)
    op.drop_column("stocks", "warehouse_id")
