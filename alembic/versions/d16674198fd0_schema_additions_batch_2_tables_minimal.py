"""schema additions batch-2 (tables minimal) — CI-safe & idempotent

Revision ID: d16674198fd0
Revises: 6869fc360d86
Create Date: 2025-10-??:??:??
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision: str = "d16674198fd0"
down_revision: str | None = "6869fc360d86"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # 这里保留“最小建表 + 索引”逻辑；均做 IF NOT EXISTS 守卫，避免重复执行
    conn.execute(
        sa.text("""
    DO $$
    BEGIN
      -- parties
      IF to_regclass('public.parties') IS NULL THEN
        CREATE TABLE public.parties (
          id   BIGINT PRIMARY KEY,
          name TEXT,
          party_type TEXT
        );
      END IF;
      -- 索引守卫
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_parties_id') THEN
        CREATE INDEX ix_parties_id ON public.parties (id);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_parties_name') THEN
        CREATE INDEX ix_parties_name ON public.parties (name);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_parties_type') THEN
        CREATE INDEX ix_parties_type ON public.parties (party_type);
      END IF;

      -- return_records
      IF to_regclass('public.return_records') IS NULL THEN
        CREATE TABLE public.return_records (
          id BIGINT PRIMARY KEY,
          order_id BIGINT,
          product_id BIGINT
        );
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_return_records_id') THEN
        CREATE INDEX ix_return_records_id ON public.return_records (id);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_return_records_order') THEN
        CREATE INDEX ix_return_records_order ON public.return_records (order_id);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_return_records_product') THEN
        CREATE INDEX ix_return_records_product ON public.return_records (product_id);
      END IF;

      -- inventory_movements（有的环境可能未用到；仍做守卫）
      IF to_regclass('public.inventory_movements') IS NULL THEN
        CREATE TABLE public.inventory_movements (
          id BIGINT PRIMARY KEY,
          item_sku TEXT,
          movement_type TEXT,
          timestamp TIMESTAMPTZ
        );
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_inventory_movements_id') THEN
        CREATE INDEX ix_inventory_movements_id ON public.inventory_movements (id);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_inventory_movements_item_sku') THEN
        CREATE INDEX ix_inventory_movements_item_sku ON public.inventory_movements (item_sku);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_inventory_movements_move_type') THEN
        CREATE INDEX ix_inventory_movements_move_type ON public.inventory_movements (movement_type);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_inventory_movements_sku_time') THEN
        CREATE INDEX ix_inventory_movements_sku_time ON public.inventory_movements (item_sku, timestamp);
      END IF;
      IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='ix_inventory_movements_type_time') THEN
        CREATE INDEX ix_inventory_movements_type_time ON public.inventory_movements (movement_type, timestamp);
      END IF;
    END$$;
    """)
    )


def downgrade() -> None:
    conn = op.get_bind()

    # 逐个资源做“有才删”；优先删索引，再删表；任何异常均吞并并 NOTICE
    conn.execute(
        sa.text("""
    DO $$
    DECLARE
      ix TEXT;
    BEGIN
      -- ==== inventory_movements 索引与表 ====
      FOREACH ix IN ARRAY ARRAY[
        'ix_inventory_movements_type_time',
        'ix_inventory_movements_sku_time',
        'ix_inventory_movements_move_type',
        'ix_inventory_movements_item_sku',
        'ix_inventory_movements_id'
      ]
      LOOP
        BEGIN
          EXECUTE format('DROP INDEX IF EXISTS public.%I', ix);
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'skip drop index % due to dependency', ix;
        END;
      END LOOP;

      IF to_regclass('public.inventory_movements') IS NOT NULL THEN
        BEGIN
          EXECUTE 'DROP TABLE public.inventory_movements';
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'skip drop table inventory_movements due to dependency';
        END;
      END IF;

      -- ==== return_records 索引与表 ====
      FOREACH ix IN ARRAY ARRAY[
        'ix_return_records_product',
        'ix_return_records_order',
        'ix_return_records_id'
      ]
      LOOP
        BEGIN
          EXECUTE format('DROP INDEX IF EXISTS public.%I', ix);
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'skip drop index % due to dependency', ix;
        END;
      END LOOP;

      IF to_regclass('public.return_records') IS NOT NULL THEN
        BEGIN
          EXECUTE 'DROP TABLE public.return_records';
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'skip drop table return_records due to dependency';
        END;
      END IF;

      -- ==== parties 索引与表 ====
      FOREACH ix IN ARRAY ARRAY[
        'ix_parties_type',
        'ix_parties_name',
        'ix_parties_id'
      ]
      LOOP
        BEGIN
          EXECUTE format('DROP INDEX IF EXISTS public.%I', ix);
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'skip drop index % due to dependency', ix;
        END;
      END LOOP;

      IF to_regclass('public.parties') IS NOT NULL THEN
        BEGIN
          EXECUTE 'DROP TABLE public.parties';
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'skip drop table parties due to dependency';
        END;
      END IF;

    END$$;
    """)
    )
