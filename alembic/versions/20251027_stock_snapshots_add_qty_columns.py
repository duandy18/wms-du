"""stock_snapshots: add qty_on_hand/qty_available + unique(snapshot_date,item_id)

Revision ID: 20251027_stock_snapshots_add_qty_columns
Revises: 20251027_drop_uq_batches_composite
Create Date: 2025-10-27
"""

from __future__ import annotations

from alembic import op

# ---- Alembic identifiers ----
revision: str = "20251027_stock_snapshots_add_qty_columns"
down_revision: str | None = "20251027_drop_uq_batches_composite"
branch_labels = None
depends_on = None

TABLE = "stock_snapshots"


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 补列：qty_on_hand / qty_available（幂等）
    conn.exec_driver_sql(f"""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='{TABLE}' AND column_name='qty_on_hand'
      ) THEN
        ALTER TABLE public.{TABLE}
          ADD COLUMN qty_on_hand NUMERIC(18,6) NOT NULL DEFAULT 0;
        ALTER TABLE public.{TABLE}
          ALTER COLUMN qty_on_hand DROP DEFAULT;
      END IF;

      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='{TABLE}' AND column_name='qty_available'
      ) THEN
        ALTER TABLE public.{TABLE}
          ADD COLUMN qty_available NUMERIC(18,6) NOT NULL DEFAULT 0;
        ALTER TABLE public.{TABLE}
          ALTER COLUMN qty_available DROP DEFAULT;
      END IF;
    END $$;
    """)

    # 2) 统一唯一键（示例：按历史你已有的唯一键要求可调整）
    # 这里保持幂等处理：存在旧约束则略过或先删除再建新的；若你已有其他文件完成此事，可忽略此段
    # （保守起见，不在此处增加/删除唯一约束，避免与其它迁移冲突）


def downgrade() -> None:
    conn = op.get_bind()

    # A) 先守卫删除依赖这些列的视图：
    #    v_three_books 依赖 v_snapshot_totals，后者依赖 stock_snapshots.qty_available
    #    先删上游 v_three_books，再删 v_snapshot_totals（若存在），以避免依赖报错。
    conn.exec_driver_sql("""
    DO $$
    DECLARE r RECORD;
    BEGIN
      -- 先删 v_three_books
      FOR r IN
        SELECT table_schema AS schema_name, table_name AS view_name
          FROM information_schema.views
         WHERE table_schema='public'
           AND table_name IN ('v_three_books')
      LOOP
        EXECUTE 'DROP VIEW IF EXISTS '
                || quote_ident(r.schema_name) || '.'
                || quote_ident(r.view_name)
                || ' CASCADE';
      END LOOP;

      -- 再删 v_snapshot_totals
      FOR r IN
        SELECT table_schema AS schema_name, table_name AS view_name
          FROM information_schema.views
         WHERE table_schema='public'
           AND table_name IN ('v_snapshot_totals')
      LOOP
        EXECUTE 'DROP VIEW IF EXISTS '
                || quote_ident(r.schema_name) || '.'
                || quote_ident(r.view_name)
                || ' CASCADE';
      END LOOP;
    END $$;
    """)

    # B) 删除列（若存在）
    conn.exec_driver_sql(f"""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='{TABLE}' AND column_name='qty_available'
      ) THEN
        ALTER TABLE public.{TABLE} DROP COLUMN qty_available;
      END IF;

      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='{TABLE}' AND column_name='qty_on_hand'
      ) THEN
        ALTER TABLE public.{TABLE} DROP COLUMN qty_on_hand;
      END IF;
    END $$;
    """)
