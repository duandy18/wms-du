"""batches: add mfg_date (production date) and supplier_lot; create helpful indexes

Why:
- FEFO 与业务分析需要生产日期（mfg_date）和可选厂商批号（supplier_lot）。
- 不做任何数据回填；仅提供结构与查询索引，后续由业务/任务逐步补齐数据。
"""

from alembic import op

# 按你的链路保持不变
revision = "20251110_batches_add_mfg_and_lot"
down_revision = "20251109_merge_phase3"
branch_labels = None
depends_on = None


def upgrade():
    # 1) 新增列（幂等：IF NOT EXISTS）
    op.execute(
        """
        ALTER TABLE batches
          ADD COLUMN IF NOT EXISTS mfg_date date,
          ADD COLUMN IF NOT EXISTS supplier_lot text;
        """
    )

    # 2) 查询索引（幂等：若已存在则跳过）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
             WHERE schemaname='public' AND tablename='batches'
               AND indexname='ix_batches_mfg_date'
          ) THEN
            CREATE INDEX ix_batches_mfg_date
              ON batches (item_id, warehouse_id, location_id, mfg_date);
          END IF;

          IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
             WHERE schemaname='public' AND tablename='batches'
               AND indexname='ix_batches_supplier_lot'
          ) THEN
            CREATE INDEX ix_batches_supplier_lot
              ON batches (item_id, warehouse_id, location_id, supplier_lot);
          END IF;
        END $$;
        """
    )


def downgrade():
    # 按逆序回滚：先删索引，再删列（幂等保护）
    op.execute(
        """
        DROP INDEX IF EXISTS ix_batches_supplier_lot;
        DROP INDEX IF EXISTS ix_batches_mfg_date;

        ALTER TABLE batches
          DROP COLUMN IF EXISTS supplier_lot,
          DROP COLUMN IF EXISTS mfg_date;
        """
    )
