"""stock_ledger: add location_id + backfill; create inventory_movements

Revision ID: b17d20cf69a3
Revises: 20251101_v_scan_trace_relaxed_join
Create Date: 2025-11-01 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b17d20cf69a3"
down_revision = "20251101_v_scan_trace_relaxed_join"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ---------------------------
    # A) stock_ledger.location_id
    # ---------------------------
    # 1) 若缺列则添加
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema='public'
                   AND table_name='stock_ledger'
                   AND column_name='location_id'
              ) THEN
                ALTER TABLE public.stock_ledger
                ADD COLUMN location_id INTEGER NULL;
              END IF;
            END $$;
            """
        )
    )

    # 2) 回填（通过 stock_id -> stocks(location_id)）
    #    - 仅当 stock_ledger 有 stock_id 列，且 location_id 仍为 NULL 时才回填
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema='public'
                   AND table_name='stock_ledger'
                   AND column_name='stock_id'
              ) THEN
                UPDATE public.stock_ledger l
                   SET location_id = s.location_id
                  FROM public.stocks s
                 WHERE l.location_id IS NULL
                   AND l.stock_id = s.id;
              END IF;
            END $$;
            """
        )
    )

    # 3) 可选：将其设为 NOT NULL（如果你的基线允许且数据完整）
    #    这一步加守卫，只在没有 NULL 的情况下加约束，以免线上炸掉
    op.execute(
        sa.text(
            """
            DO $$
            DECLARE v_missing_count bigint;
            BEGIN
              SELECT COUNT(*) INTO v_missing_count
                FROM public.stock_ledger
               WHERE location_id IS NULL;

              IF v_missing_count = 0 THEN
                -- 如果之前没加过约束，尝试设为 NOT NULL
                BEGIN
                  ALTER TABLE public.stock_ledger
                    ALTER COLUMN location_id SET NOT NULL;
                EXCEPTION WHEN others THEN
                  -- 兼容老版本/其他分支的历史，忽略失败即可
                  NULL;
                END;
              END IF;
            END $$;
            """
        )
    )

    # 4) 索引（幂等）
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                 WHERE schemaname='public' AND indexname='ix_stock_ledger_location_id'
              ) THEN
                CREATE INDEX ix_stock_ledger_location_id
                    ON public.stock_ledger(location_id);
              END IF;
            END $$;
            """
        )
    )

    # -------------------------------------
    # B) inventory_movements（新增审计流水）
    # -------------------------------------
    # 统一采用 Numeric(18,6) 的 qty，避免浮点误差；并增加幂等唯一约束
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF to_regclass('public.inventory_movements') IS NULL THEN
                CREATE TABLE public.inventory_movements (
                  id           SERIAL PRIMARY KEY,
                  item_id      INTEGER      NOT NULL,
                  location_id  INTEGER      NOT NULL,
                  batch_code   VARCHAR(64)  NULL,
                  qty          NUMERIC(18,6) NOT NULL,
                  reason       VARCHAR(32)  NOT NULL,
                  ref          VARCHAR(255) NULL,
                  occurred_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
                );
              END IF;

              -- 幂等 UQ
              IF NOT EXISTS (
                SELECT 1
                  FROM pg_constraint
                 WHERE conname='uq_inv_mov_idem_reason_ref_target'
                   AND conrelid = 'public.inventory_movements'::regclass
              ) THEN
                ALTER TABLE public.inventory_movements
                  ADD CONSTRAINT uq_inv_mov_idem_reason_ref_target
                  UNIQUE (reason, ref, item_id, location_id, batch_code);
              END IF;

              -- 常用索引
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                 WHERE schemaname='public' AND indexname='ix_inv_mov_item_loc_time'
              ) THEN
                CREATE INDEX ix_inv_mov_item_loc_time
                    ON public.inventory_movements(item_id, location_id, occurred_at);
              END IF;

              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                 WHERE schemaname='public' AND indexname='ix_inv_mov_reason_ref'
              ) THEN
                CREATE INDEX ix_inv_mov_reason_ref
                    ON public.inventory_movements(reason, ref);
              END IF;

              -- 便于按批次定位（与 FEFO 对齐）
              IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                 WHERE schemaname='public' AND indexname='ix_inv_mov_batch'
              ) THEN
                CREATE INDEX ix_inv_mov_batch
                    ON public.inventory_movements(batch_code);
              END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    # 降级时按相反顺序做清理，并加守卫

    # B) inventory_movements 表及索引/约束
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF to_regclass('public.inventory_movements') IS NOT NULL THEN
                -- 索引/约束可不显式逐一删除，DROP TABLE 会一并清理；为了可读性保留守卫式删除
                BEGIN EXECUTE 'DROP INDEX IF EXISTS public.ix_inv_mov_item_loc_time'; EXCEPTION WHEN others THEN NULL; END;
                BEGIN EXECUTE 'DROP INDEX IF EXISTS public.ix_inv_mov_reason_ref';   EXCEPTION WHEN others THEN NULL; END;
                BEGIN EXECUTE 'DROP INDEX IF EXISTS public.ix_inv_mov_batch';        EXCEPTION WHEN others THEN NULL; END;
                BEGIN EXECUTE 'ALTER TABLE public.inventory_movements DROP CONSTRAINT IF EXISTS uq_inv_mov_idem_reason_ref_target'; EXCEPTION WHEN others THEN NULL; END;
                DROP TABLE IF EXISTS public.inventory_movements;
              END IF;
            END $$;
            """
        )
    )

    # A) stock_ledger.location_id 索引
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM pg_indexes
                 WHERE schemaname='public' AND indexname='ix_stock_ledger_location_id'
              ) THEN
                DROP INDEX public.ix_stock_ledger_location_id;
              END IF;
            END $$;
            """
        )
    )

    # A) stock_ledger.location_id 列（降级为 NULL/可删除）
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1
                  FROM information_schema.columns
                 WHERE table_schema='public'
                   AND table_name='stock_ledger'
                   AND column_name='location_id'
              ) THEN
                -- 先放开 NOT NULL（若之前设置过）
                BEGIN
                  ALTER TABLE public.stock_ledger
                    ALTER COLUMN location_id DROP NOT NULL;
                EXCEPTION WHEN others THEN
                  NULL;
                END;
                -- 再删列
                ALTER TABLE public.stock_ledger
                  DROP COLUMN IF EXISTS location_id;
              END IF;
            END $$;
            """
        )
    )
