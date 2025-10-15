"""create batches table if missing (idempotent)

Revision ID: 20251015_create_batches_if_missing
Revises: 20251015_widen_alembic_version_len
Create Date: 2025-10-15
"""
from alembic import op

revision = "20251015_create_batches_if_missing"
down_revision = "20251015_widen_alembic_version_len"  # ← 你当前的最新修订
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 仅当 batches 不存在时创建（幂等）
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.batches') IS NULL THEN
            CREATE TABLE public.batches (
              id              SERIAL PRIMARY KEY,
              item_id         INTEGER NOT NULL,
              warehouse_id    INTEGER NOT NULL,
              location_id     INTEGER NOT NULL,
              batch_code      VARCHAR(64) NOT NULL,
              production_date DATE NULL,
              expiry_date     DATE NULL
            );
          END IF;
        END$$;
        """
    )

    # 幂等唯一键：与你先前迁移的复合键保持一致（若已存在则跳过）
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.batches') IS NOT NULL THEN
            IF NOT EXISTS (
              SELECT 1 FROM pg_constraint
              WHERE conname = 'uq_batches_composite'
                AND conrelid = 'public.batches'::regclass
            ) THEN
              ALTER TABLE public.batches
                ADD CONSTRAINT uq_batches_composite
                UNIQUE (item_id, warehouse_id, location_id, batch_code, production_date, expiry_date);
            END IF;

            -- 常用查询索引（非唯一）
            IF NOT EXISTS (
              SELECT 1 FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
              WHERE c.relkind='i' AND c.relname='ix_batches_composite'
                AND n.nspname='public'
            ) THEN
              CREATE INDEX ix_batches_composite
              ON public.batches (item_id, warehouse_id, location_id, batch_code, production_date, expiry_date);
            END IF;
          END IF;
        END$$;
        """
    )

    # 可选：若 stock_ledger.batch_id 存在，补外键到 batches.id（幂等）
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.batches') IS NOT NULL
             AND EXISTS (
               SELECT 1 FROM information_schema.columns
               WHERE table_schema='public' AND table_name='stock_ledger' AND column_name='batch_id'
             ) THEN
            IF NOT EXISTS (
              SELECT 1 FROM pg_constraint
              WHERE conname='fk_stock_ledger_batch_id_batches'
                AND conrelid='public.stock_ledger'::regclass
            ) THEN
              ALTER TABLE public.stock_ledger
                ADD CONSTRAINT fk_stock_ledger_batch_id_batches
                FOREIGN KEY (batch_id) REFERENCES public.batches(id)
                ON DELETE SET NULL;
            END IF;
          END IF;
        END$$;
        """
    )


def downgrade() -> None:
    # 保守起见，不回收表；如必须回滚，可按需 DROP CONSTRAINT / DROP TABLE
    pass
