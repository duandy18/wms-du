"""fill item_id on stock_ledger insert via trigger (compat for raw SQL)"""

from alembic import op

revision = "20251015_fill_item_id_on_ledger_insert"
down_revision = "4a963ea84f28"  # 你当前唯一 head（mergepoint）
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        -- 若插入台账未提供 item_id，则由 stock_id 反查 stocks.item_id 回填
        CREATE OR REPLACE FUNCTION public.tg_stock_ledger_fill_item_id()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF NEW.item_id IS NULL THEN
            SELECT s.item_id INTO NEW.item_id
            FROM public.stocks s
            WHERE s.id = NEW.stock_id;
          END IF;
          RETURN NEW;
        END;
        $$;

        -- 幂等创建触发器
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1
            FROM pg_trigger
            WHERE tgname = 'trg_stock_ledger_fill_item_id'
              AND tgrelid = 'public.stock_ledger'::regclass
          ) THEN
            CREATE TRIGGER trg_stock_ledger_fill_item_id
            BEFORE INSERT ON public.stock_ledger
            FOR EACH ROW
            EXECUTE FUNCTION public.tg_stock_ledger_fill_item_id();
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM pg_trigger
            WHERE tgname = 'trg_stock_ledger_fill_item_id'
              AND tgrelid = 'public.stock_ledger'::regclass
          ) THEN
            DROP TRIGGER trg_stock_ledger_fill_item_id ON public.stock_ledger;
          END IF;
        END$$;

        DROP FUNCTION IF EXISTS public.tg_stock_ledger_fill_item_id();
        """
    )
