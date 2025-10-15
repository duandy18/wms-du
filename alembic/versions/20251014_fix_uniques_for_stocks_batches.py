"""fix uniques for stocks & batches (idempotent)

Revision ID: 20251014_fix_uniques_for_stocks_batches
Revises: 6e6459c3169f
Create Date: 2025-10-14
"""

from alembic import op

revision = "20251014_fix_uniques_for_stocks_batches"
down_revision = "6e6459c3169f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- stocks 相关：幂等修复 ---
    op.execute(
        """
        DO $$
        BEGIN
          -- 唯一 (item_id, location_id)
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_stocks_item_location'
              AND conrelid = 'public.stocks'::regclass
          ) THEN
            ALTER TABLE public.stocks
              ADD CONSTRAINT uq_stocks_item_location UNIQUE (item_id, location_id);
          END IF;

          -- 辅助索引（存在就跳过）
          IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind='i' AND c.relname='ix_stocks_item'
              AND n.nspname='public'
          ) THEN
            CREATE INDEX ix_stocks_item ON public.stocks(item_id);
          END IF;

          IF NOT EXISTS (
            SELECT 1 FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind='i' AND c.relname='ix_stocks_location'
              AND n.nspname='public'
          ) THEN
            CREATE INDEX ix_stocks_location ON public.stocks(location_id);
          END IF;
        END$$;
        """
    )

    # --- batches 相关：仅在表存在时执行 ---
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.batches') IS NOT NULL THEN
            -- 幂等唯一约束 (item_id, batch_code)（如果你的目标是更复杂复合键，请与实际表结构对齐）
            IF NOT EXISTS (
              SELECT 1 FROM pg_constraint
              WHERE conname = 'uq_batches_item_batch'
                AND conrelid = 'public.batches'::regclass
            ) THEN
              ALTER TABLE public.batches
                ADD CONSTRAINT uq_batches_item_batch UNIQUE (item_id, batch_code);
            END IF;
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # 一般不回滚；如需回退，可按需 drop 约束/索引
    pass
