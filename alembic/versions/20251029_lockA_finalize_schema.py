# alembic/versions/20251029_lockA_finalize_schema.py
from alembic import op
import sqlalchemy as sa

# 改成你当前唯一 head（运行 `alembic heads -v` 查看）
revision = "20251029_lockA_finalize_schema"
down_revision = "63af7f94ad50"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ========= 0) 预检查（强制存在前置表/列） =========
    # locations.warehouse_id 必须存在
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

    # 从 locations 回填（唯一权威）
    conn.exec_driver_sql("""
        UPDATE stocks s
           SET warehouse_id = l.warehouse_id
          FROM locations l
         WHERE l.id = s.location_id
           AND s.warehouse_id IS NULL;
    """)

    # 兜底：仍未回填的行挂 MAIN 仓（若无则创建）
    conn.exec_driver_sql("""
        INSERT INTO warehouses (name)
        SELECT 'MAIN'
        WHERE NOT EXISTS (SELECT 1 FROM warehouses WHERE name='MAIN');

        WITH mainw AS (SELECT id FROM warehouses WHERE name='MAIN' LIMIT 1)
        UPDATE stocks s
           SET warehouse_id = (SELECT id FROM mainw)
         WHERE s.warehouse_id IS NULL;
    """)

    # 设为 NOT NULL
    op.alter_column("stocks", "warehouse_id", nullable=False)

    # 外键（可延迟，避免事务顺序束缚）
    op.execute("""
        ALTER TABLE stocks
        ADD CONSTRAINT fk_stocks_warehouse
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
        DEFERRABLE INITIALLY DEFERRED
    """)

    # ========= 2) batches.qty 收紧为 NOT NULL（若当前允许 NULL，则统一收紧） =========
    # 将 NULL 回填为 0，然后加 NOT NULL（若已为 NOT NULL，此两步幂等）
    conn.exec_driver_sql("UPDATE batches SET qty = 0 WHERE qty IS NULL;")
    op.alter_column("batches", "qty", existing_type=sa.Integer(), nullable=False)

    # ========= 3) stocks.batch_code：新增 → 回填 → 合成批次 → 去默认 =========
    op.add_column(
        "stocks",
        sa.Column("batch_code", sa.String(length=64), nullable=False, server_default="MIG-UNSPEC"),
    )

    # “一地一批” → 用真批次码回填
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

    # 为剩余未回填的 stocks 生成“合成批次”记录（batches）—— qty=0 占位，保持一致性
    conn.exec_driver_sql("""
        INSERT INTO batches (item_id, warehouse_id, location_id, batch_code, expiry_date, qty)
        SELECT s.item_id,
               s.warehouse_id,
               s.location_id,
               CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id) AS batch_code,
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

    # 将剩余 MIG-UNSPEC 回填为合成批次码
    conn.exec_driver_sql("""
        UPDATE stocks s
           SET batch_code = CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id)
         WHERE s.batch_code = 'MIG-UNSPEC';
    """)

    # 去掉临时默认
    op.alter_column("stocks", "batch_code", server_default=None)

    # ========= 4) 约束与索引：删旧 UQ → 建索引 → 新 UQ（NOT VALID） =========
    # 删除旧的 loc-only 唯一约束
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_location")

    # batches 唯一索引（若已存在则不会重复）
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_batches_item_wh_loc_code
          ON batches (item_id, warehouse_id, location_id, batch_code)
    """)

    # stocks 复合索引
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_stocks_item_wh_loc_batch
          ON stocks (item_id, warehouse_id, location_id, batch_code)
    """)

    # stocks 新唯一约束（先 NOT VALID，待数据稳定后 VALIDATE）
    op.execute("""
        ALTER TABLE stocks
          ADD CONSTRAINT uq_stocks_item_wh_loc_code
          UNIQUE (item_id, warehouse_id, location_id, batch_code) NOT VALID
    """)


def downgrade():
    # 回滚顺序：约束/索引 → 列
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_wh_loc_code")
    op.execute("DROP INDEX IF EXISTS idx_stocks_item_wh_loc_batch")
    op.execute("DROP INDEX IF EXISTS uq_batches_item_wh_loc_code")
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS fk_stocks_warehouse")

    op.alter_column("batches", "qty", existing_type=sa.Integer(), nullable=True)

    op.drop_column("stocks", "batch_code")
    op.alter_column("stocks", "warehouse_id", nullable=True)
    op.drop_column("stocks", "warehouse_id")
