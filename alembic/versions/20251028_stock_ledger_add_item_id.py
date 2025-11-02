"""stock_ledger: add item_id (idempotent) + FK + index (CI-safe)

Revision ID: 20251028_stock_ledger_add_item_id
Revises: 20251027_stock_snapshots_add_qty_columns
Create Date: 2025-10-28
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# ---- Alembic identifiers ----
revision: str = "20251028_stock_ledger_add_item_id"
down_revision: str | None = "20251027_stock_snapshots_add_qty_columns"
branch_labels = None
depends_on = None

TABLE = "stock_ledger"
COL = "item_id"
IDX = "ix_stock_ledger_item_id"
FK  = "fk_stock_ledger_item"


def upgrade() -> None:
    conn = op.get_bind()

    # 1) 列存在性检查后添加（幂等）
    conn.exec_driver_sql(f"""
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='{TABLE}' AND column_name='{COL}'
      ) THEN
        ALTER TABLE public.{TABLE} ADD COLUMN {COL} BIGINT;
      END IF;
    END $$;
    """)

    # 2) 尝试补齐索引（幂等）
    conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {IDX} ON public.{TABLE}({COL});")

    # 3) 尝试补齐外键（目标表 items 存在时才创建；幂等）
    conn.exec_driver_sql(f"""
    DO $$
    BEGIN
      -- 目标表存在才建 FK
      IF to_regclass('public.items') IS NOT NULL THEN
        -- 若同名外键不存在则创建
        IF NOT EXISTS (
          SELECT 1
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
           WHERE t.relname='{TABLE}' AND c.conname='{FK}' AND c.contype='f'
        ) THEN
          ALTER TABLE public.{TABLE}
            ADD CONSTRAINT {FK}
            FOREIGN KEY ({COL}) REFERENCES public.items(id)
            ON DELETE SET NULL;
        END IF;
      END IF;
    END $$;
    """)

    # 4) 可选：如果历史数据缺 item_id，可在此做一次最佳努力的回填（保持幂等）
    # 这里保守起见不做回填；真实回填通常依赖 stocks / items 业务映射，放到上游脚本完成。


def downgrade() -> None:
    conn = op.get_bind()

    # A) 先守卫删除依赖此列的视图/对象（例如 v_outbound_idem_audit）
    #    注意：使用 quote_ident 防注入与转义，避免 psycopg 的占位符限制。
    conn.exec_driver_sql("""
    DO $$
    DECLARE v RECORD;
    BEGIN
      FOR v IN
        SELECT table_schema AS schema_name, table_name AS view_name
          FROM information_schema.views
         WHERE table_schema='public'
           AND table_name IN ('v_outbound_idem_audit')
      LOOP
        EXECUTE 'DROP VIEW IF EXISTS '
                || quote_ident(v.schema_name) || '.'
                || quote_ident(v.view_name)
                || ' CASCADE';
      END LOOP;
    END $$;
    """)

    # B) 先删索引（若存在）
    conn.exec_driver_sql(f"DROP INDEX IF EXISTS public.{IDX};")

    # C) 再删外键（若存在）
    conn.exec_driver_sql(f"""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t ON t.oid=c.conrelid
         WHERE t.relname='{TABLE}' AND c.conname='{FK}' AND c.contype='f'
      ) THEN
        ALTER TABLE public.{TABLE} DROP CONSTRAINT {FK};
      END IF;
    END $$;
    """)

    # D) 最后删除列（若存在）
    conn.exec_driver_sql(f"""
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema='public' AND table_name='{TABLE}' AND column_name='{COL}'
      ) THEN
        ALTER TABLE public.{TABLE} DROP COLUMN {COL};
      END IF;
    END $$;
    """)
