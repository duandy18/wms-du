"""Lock-A finalize schema: strong uniques + warehouse_id/batch_code wiring (CI-safe)

Revision ID: 20251029_lockA_finalize_schema
Revises: 63af7f94ad50
Create Date: 2025-10-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20251029_lockA_finalize_schema"
down_revision = "63af7f94ad50"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # ========= 0) 预检查：locations.warehouse_id 必须存在 =========
    conn.exec_driver_sql(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='locations' AND column_name='warehouse_id'
          ) THEN
            RAISE EXCEPTION 'locations.warehouse_id is required by Lock-A migration.';
          END IF;
        END $$;
        """
    )

    # ========= 1) stocks.warehouse_id：ADD IF NOT EXISTS → 回填 → NOT NULL → 外键 =========
    op.execute("ALTER TABLE public.stocks ADD COLUMN IF NOT EXISTS warehouse_id INTEGER")

    # 回填仓库
    conn.exec_driver_sql(
        """
        UPDATE public.stocks s
           SET warehouse_id = l.warehouse_id
          FROM public.locations l
         WHERE l.id = s.location_id
           AND s.warehouse_id IS NULL;
        """
    )

    # 兜底 MAIN 仓（幂等）
    conn.exec_driver_sql(
        """
        INSERT INTO public.warehouses (name)
        SELECT 'MAIN'
        WHERE NOT EXISTS (SELECT 1 FROM public.warehouses WHERE name='MAIN');

        WITH mainw AS (SELECT id FROM public.warehouses WHERE name='MAIN' LIMIT 1)
        UPDATE public.stocks s
           SET warehouse_id = (SELECT id FROM mainw)
         WHERE s.warehouse_id IS NULL;
        """
    )

    op.execute("ALTER TABLE public.stocks ALTER COLUMN warehouse_id SET NOT NULL")

    # 外键（若不存在则创建；DEFERRABLE）
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE table_schema='public' AND table_name='stocks' AND constraint_name='fk_stocks_warehouse'
          ) THEN
            ALTER TABLE public.stocks
              ADD CONSTRAINT fk_stocks_warehouse
              FOREIGN KEY (warehouse_id) REFERENCES public.warehouses(id)
              DEFERRABLE INITIALLY DEFERRED;
          END IF;
        END $$;
        """
    )

    # ========= 2) batches.qty 收紧为 NOT NULL（先清 NULL） =========
    conn.exec_driver_sql("UPDATE public.batches SET qty = 0 WHERE qty IS NULL;")
    op.execute("ALTER TABLE public.batches ALTER COLUMN qty SET NOT NULL")

    # ========= 3) stocks.batch_code：ADD IF NOT EXISTS → 回填 → 合成批次 → DROP DEFAULT =========
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name='stocks' AND column_name='batch_code'
          ) THEN
            ALTER TABLE public.stocks
              ADD COLUMN batch_code VARCHAR(64) NOT NULL DEFAULT 'MIG-UNSPEC';
          END IF;
        END $$;
        """
    )

    # “一地一批” → 用真批次码回填
    conn.exec_driver_sql(
        """
        WITH one AS (
          SELECT item_id, warehouse_id, location_id, MIN(batch_code) AS batch_code
            FROM public.batches
           GROUP BY item_id, warehouse_id, location_id
          HAVING COUNT(*) = 1
        )
        UPDATE public.stocks s
           SET batch_code = o.batch_code
          FROM one o
         WHERE s.item_id = o.item_id
           AND s.warehouse_id = o.warehouse_id
           AND s.location_id = o.location_id
           AND s.batch_code = 'MIG-UNSPEC';
        """
    )

    # 为剩余未回填的 stocks 生成“合成批次”（幂等）
    conn.exec_driver_sql(
        """
        INSERT INTO public.batches (item_id, warehouse_id, location_id, batch_code, expiry_date, qty)
        SELECT s.item_id,
               s.warehouse_id,
               s.location_id,
               CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id),
               NULL::date,
               0
          FROM public.stocks s
     LEFT JOIN public.batches b
            ON b.item_id = s.item_id
           AND b.warehouse_id = s.warehouse_id
           AND b.location_id = s.location_id
           AND b.batch_code = CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id)
         WHERE s.batch_code = 'MIG-UNSPEC'
           AND b.item_id IS NULL
        ON CONFLICT DO NOTHING;
        """
    )

    # 将剩余 MIG-UNSPEC 回填为合成批次码（幂等）
    conn.exec_driver_sql(
        """
        UPDATE public.stocks s
           SET batch_code = CONCAT('MIG-', s.item_id, '-', s.warehouse_id, '-', s.location_id)
         WHERE s.batch_code = 'MIG-UNSPEC';
        """
    )

    # NOT NULL
    op.execute("ALTER TABLE public.stocks ALTER COLUMN batch_code SET NOT NULL")

    # 在单独事务块里 DROP DEFAULT（若存在）
    ctx = op.get_context()
    with ctx.autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='stocks' AND column_name='batch_code' AND column_default IS NOT NULL
              ) THEN
                ALTER TABLE public.stocks ALTER COLUMN batch_code DROP DEFAULT;
              END IF;
            END $$;
            """
        )

    # ========= 4) 约束与索引：删旧 UQ → 建索引 → 唯一约束（USING INDEX） =========
    op.execute("ALTER TABLE public.stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_location")

    # batches UQ 索引（若不存在则创建）
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_batches_item_wh_loc_code
          ON public.batches (item_id, warehouse_id, location_id, batch_code)
        """
    )

    # stocks 非唯一查询索引
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_stocks_item_wh_loc_batch
          ON public.stocks (item_id, warehouse_id, location_id, batch_code)
        """
    )

    # stocks 唯一索引 + 绑定唯一约束
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_class WHERE relkind='i' AND relname='uq_stocks_item_wh_loc_code_idx'
          ) THEN
            CREATE UNIQUE INDEX uq_stocks_item_wh_loc_code_idx
              ON public.stocks (item_id, warehouse_id, location_id, batch_code);
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='uq_stocks_item_wh_loc_code'
          ) THEN
            ALTER TABLE public.stocks
              ADD CONSTRAINT uq_stocks_item_wh_loc_code
              UNIQUE USING INDEX uq_stocks_item_wh_loc_code_idx;
          END IF;
        END $$;
        """
    )


def downgrade():
    conn = op.get_bind()

    # ========= A) 先清理依赖于 stocks.batch_code 的视图，避免 DependentObjectsStillExist =========
    # 注意：不要在 SQL 字符串里出现 %I；改用 quote_ident 拼接，避免 psycopg 误把 %I 当 DBAPI 占位符。
    conn.exec_driver_sql(
        """
        DO $$
        DECLARE v RECORD;
        BEGIN
          FOR v IN
            SELECT table_schema AS schema_name, table_name AS view_name
              FROM information_schema.views
             WHERE table_schema = 'public'
               AND table_name IN ('v_putaway_ledger_recent')
          LOOP
            EXECUTE 'DROP VIEW IF EXISTS '
                    || quote_ident(v.schema_name) || '.'
                    || quote_ident(v.view_name) || ' CASCADE';
          END LOOP;
        END $$;
        """
    )

    # ========= B) 先删 stocks 上的唯一约束/索引/普通索引（若存在） =========
    op.execute("ALTER TABLE public.stocks DROP CONSTRAINT IF EXISTS uq_stocks_item_wh_loc_code")
    op.execute("DROP INDEX IF EXISTS public.uq_stocks_item_wh_loc_code_idx")
    op.execute("DROP INDEX IF EXISTS public.idx_stocks_item_wh_loc_batch")

    # ========= C) 再处理 batches 侧唯一约束/唯一索引 =========
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_constraint c
              JOIN pg_class t ON t.oid = c.conrelid
             WHERE t.relname = 'batches'
               AND c.conname = 'uq_batches_item_wh_loc_code'
               AND c.contype = 'u'
          ) THEN
            ALTER TABLE public.batches DROP CONSTRAINT uq_batches_item_wh_loc_code;
          END IF;
        END $$;
        """
    )
    op.execute("DROP INDEX IF EXISTS public.uq_batches_item_wh_loc_code")

    # ========= D) 解除外键 & 回滚列属性 =========
    op.execute("ALTER TABLE public.stocks DROP CONSTRAINT IF EXISTS fk_stocks_warehouse")

    op.execute("ALTER TABLE public.batches ALTER COLUMN qty DROP NOT NULL")

    op.execute("ALTER TABLE public.stocks ALTER COLUMN batch_code DROP NOT NULL")
    op.execute("ALTER TABLE public.stocks DROP COLUMN IF EXISTS batch_code")

    op.execute("ALTER TABLE public.stocks ALTER COLUMN warehouse_id DROP NOT NULL")
    op.execute("ALTER TABLE public.stocks DROP COLUMN IF EXISTS warehouse_id")
