"""phase3: add stocks.qty int & backfill from qty_on_hand"""
from alembic import op
import sqlalchemy as sa

# 按你当前 heads 输出设置
revision = "20251111_add_stocks_qty_int"
down_revision = "20251111_add_ix_batches_item_id"
branch_labels = None
depends_on = None

def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
          -- 1) 若缺列则添加（int 与现有口径一致）
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='stocks' AND column_name='qty'
          ) THEN
            ALTER TABLE stocks
              ADD COLUMN qty integer NOT NULL DEFAULT 0;
          END IF;

          -- 2) 回填：以旧口径 qty_on_hand 为准
          --    若不存在 qty_on_hand 列，则忽略更新（当前库存在）
          BEGIN
            EXECUTE 'UPDATE stocks SET qty = COALESCE(qty_on_hand, qty, 0)';
          EXCEPTION WHEN undefined_column THEN
            NULL;
          END;

          -- 3) 去掉默认值，避免后续写入时被默认覆盖
          ALTER TABLE stocks ALTER COLUMN qty DROP DEFAULT;
        END $$;
        """
    )

def downgrade():
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='stocks' AND column_name='qty'
          ) THEN
            ALTER TABLE stocks DROP COLUMN qty;
          END IF;
        END $$;
        """
    )
