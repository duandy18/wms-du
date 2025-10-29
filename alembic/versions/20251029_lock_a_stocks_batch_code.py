# alembic/versions/20251029_lock_a_stocks_batch_code.py
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251029_lock_a_stocks_batch_code"
down_revision = "63af7f94ad50"   # 原来是 None 或 <base>，改成主线最新 head
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1) 加列（临时默认，避免 NOT NULL 阻塞）
    op.add_column(
        "stocks",
        sa.Column("batch_code", sa.String(length=64), nullable=False, server_default="MIG-UNSPEC"),
    )

    # 2) 对“一地一批”的场景，用真实批次回填
    conn.exec_driver_sql(
        """
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
          AND COALESCE(s.warehouse_id, -1) = COALESCE(o.warehouse_id, -1)
          AND s.location_id = o.location_id
          AND s.batch_code = 'MIG-UNSPEC'
        """
    )

    # 3) 为剩余未回填的行生成合成批次（避免中断业务）
    conn.exec_driver_sql(
        """
        INSERT INTO batches (item_id, warehouse_id, location_id, batch_code, expiry_date)
        SELECT s.item_id,
               s.warehouse_id,
               s.location_id,
               CONCAT('MIG-', s.item_id, '-', COALESCE(s.warehouse_id,0), '-', s.location_id) AS batch_code,
               NULL::date
        FROM stocks s
        LEFT JOIN batches b
          ON b.item_id = s.item_id
         AND COALESCE(b.warehouse_id, -1) = COALESCE(s.warehouse_id, -1)
         AND b.location_id = s.location_id
         AND b.batch_code = CONCAT('MIG-', s.item_id, '-', COALESCE(s.warehouse_id,0), '-', s.location_id)
        WHERE s.batch_code = 'MIG-UNSPEC'
          AND b.item_id IS NULL
        ON CONFLICT DO NOTHING
        """
    )

    # 4) 将剩余的 MIG-UNSPEC 回填为合成批次码
    conn.exec_driver_sql(
        """
        UPDATE stocks s
        SET batch_code = CONCAT('MIG-', s.item_id, '-', COALESCE(s.warehouse_id,0), '-', s.location_id)
        WHERE s.batch_code = 'MIG-UNSPEC'
        """
    )

    # 5) 索引与“非验证”唯一约束（后续可在线 VALIDATE）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stocks_item_loc_batch ON stocks (item_id, warehouse_id, location_id, batch_code)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_batches_item_wh_loc_code ON batches (item_id, warehouse_id, location_id, batch_code)"
    )
    # stocks 唯一约束先 NOT VALID，等你数据确认后再 VALIDATE
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'uq_stocks_item_wh_loc_code'
          ) THEN
            ALTER TABLE stocks
              ADD CONSTRAINT uq_stocks_item_wh_loc_code
              UNIQUE (item_id, warehouse_id, location_id, batch_code) NOT VALID;
          END IF;
        END $$;
        """
    )

    # 6) 清除临时默认
    op.alter_column("stocks", "batch_code", server_default=None)


def downgrade():
    conn = op.get_bind()
    # 尝试移除唯一约束与索引
    op.execute("ALTER TABLE stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_wh_loc_code")
    op.execute("DROP INDEX IF EXISTS idx_stocks_item_loc_batch")
    # 不动 batches 的 UQ（可能已有依赖）
    op.drop_column("stocks", "batch_code")
