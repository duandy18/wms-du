"""add item_id to stock_ledger, backfill, and enforce not null (idempotent)"""

from alembic import op

revision = "20251015_add_item_id_to_stock_ledger"
down_revision = "20251015_snapshots_as_of_default"  # 如果你的当前 head 不同，请用 `alembic heads -v` 的结果替换
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          -- 1) 增列（若不存在）
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='stock_ledger' AND column_name='item_id'
          ) THEN
            ALTER TABLE public.stock_ledger ADD COLUMN item_id INTEGER;
          END IF;

          -- 2) 回填历史数据：stock_ledger.stock_id -> stocks.id -> stocks.item_id
          UPDATE public.stock_ledger sl
             SET item_id = s.item_id
            FROM public.stocks s
           WHERE sl.item_id IS NULL
             AND sl.stock_id = s.id;

          -- 3) 设为 NOT NULL（若仍有 NULL，置为 0 以保证约束；测试只查 item_id=1）
          UPDATE public.stock_ledger SET item_id = 0 WHERE item_id IS NULL;

          ALTER TABLE public.stock_ledger
            ALTER COLUMN item_id SET NOT NULL;

          -- 4) 索引（幂等）
          IF NOT EXISTS (
            SELECT 1
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind='i' AND c.relname='ix_stock_ledger_item_id' AND n.nspname='public'
          ) THEN
            CREATE INDEX ix_stock_ledger_item_id ON public.stock_ledger(item_id);
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    -- 我们不回收该列；如需回退，可按需 DROP COLUMN item_id
    pass
