"""unify unique key for batches and dedupe, then add constraint

Revision ID: 20251014_uq_batches_composite
Revises: 20251014_uq_ledger_reason_ref_refline
Create Date: 2025-10-14
"""

from alembic import op

revision = "20251014_uq_batches_composite"
down_revision = "20251014_uq_ledger_reason_ref_refline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 仅当 batches 表存在时才执行；否则跳过
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.batches') IS NOT NULL THEN

            -- 1) 批次去重（同键项只保留 keep_id）
            --    若 stock_ledger 存在 batch_id 列，则回写到台账；否则跳过回写步骤
            IF EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema='public'
                AND table_name='stock_ledger'
                AND column_name='batch_id'
            ) THEN
              WITH grp AS (
                SELECT
                  id, item_id, warehouse_id, location_id, batch_code, production_date, expiry_date,
                  MIN(id) OVER (
                    PARTITION BY item_id, warehouse_id, location_id, batch_code, production_date, expiry_date
                  ) AS keep_id
                FROM public.batches
              ),
              losers AS (
                SELECT id, keep_id FROM grp WHERE id <> keep_id
              )
              UPDATE public.stock_ledger AS sl
                 SET batch_id = l.keep_id
                FROM losers l
               WHERE sl.batch_id = l.id;
            END IF;

            -- 2) 删除批次表中重复的“败者”行（若存在）
            DELETE FROM public.batches b
            USING (
              SELECT id, keep_id
              FROM (
                SELECT
                  id, item_id, warehouse_id, location_id, batch_code, production_date, expiry_date,
                  MIN(id) OVER (
                    PARTITION BY item_id, warehouse_id, location_id, batch_code, production_date, expiry_date
                  ) AS keep_id
                FROM public.batches
              ) t
              WHERE id <> keep_id
            ) d
            WHERE b.id = d.id;

            -- 3) 幂等创建唯一约束（复合键：item, warehouse, location, code, prod_date, exp_date）
            IF NOT EXISTS (
              SELECT 1
              FROM   pg_constraint
              WHERE  conname = 'uq_batches_composite'
              AND    conrelid = 'public.batches'::regclass
            ) THEN
              ALTER TABLE public.batches
                ADD CONSTRAINT uq_batches_composite
                UNIQUE (item_id, warehouse_id, location_id, batch_code, production_date, expiry_date);
            END IF;

            -- 4) 为查询友好，幂等加一个覆盖索引（非唯一）
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


def downgrade() -> None:
    # 通常不回滚批次唯一键；如真要回退，可按需删除约束/索引
    pass
