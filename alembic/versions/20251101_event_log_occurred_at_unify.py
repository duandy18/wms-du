"""Unify event time: add occurred_at (timestamptz) to event_log & event_error_log

Revision ID: 20251101_event_log_occurred_at_unify
Revises: 20251031_merge_scan_views_and_loc_trigger
Create Date: 2025-11-01 22:10:00
"""
from alembic import op
import sqlalchemy as sa

# --- Alembic identifiers ---
revision = "20251101_event_log_occurred_at_unify"
down_revision = "20251031_merge_scan_views_and_loc_trigger"
branch_labels = None
depends_on = None


def _has_column(conn, table_name: str, column_name: str) -> bool:
    sql = sa.text(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema='public'
           AND table_name=:t
           AND column_name=:c
        """
    )
    row = conn.execute(sql, {"t": table_name, "c": column_name}).fetchone()
    return row is not None


def upgrade():
    conn = op.get_bind()

    # 1) 添加列（若不存在），两张表统一口径
    for tbl in ("event_log", "event_error_log"):
        op.execute(
            f"""
            ALTER TABLE {tbl}
            ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ
            """
        )

    # 2) 历史回填：仅把 NULL 行补齐
    #    优先顺序：meta.occurred_at（ISO8601）→ created_at（若存在）→ now()
    for tbl in ("event_log", "event_error_log"):
        has_created_at = _has_column(conn, tbl, "created_at")
        has_meta = _has_column(conn, tbl, "meta")

        # 构造 meta 时间提取表达式；若无 meta 列则置为 NULL
        meta_expr = (
            "NULLIF(TRIM(BOTH FROM (meta->>'occurred_at')), '')::timestamptz"
            if has_meta
            else "NULL"
        )

        if has_created_at:
            backfill_sql = f"""
                UPDATE {tbl}
                   SET occurred_at = COALESCE(
                       {meta_expr},
                       created_at,
                       now()
                   )
                 WHERE occurred_at IS NULL
            """
        else:
            backfill_sql = f"""
                UPDATE {tbl}
                   SET occurred_at = COALESCE(
                       {meta_expr},
                       now()
                   )
                 WHERE occurred_at IS NULL
            """
        op.execute(backfill_sql)

    # 3) 设为 NOT NULL（若之前允许为空，这里统一上锁）
    for tbl in ("event_log", "event_error_log"):
        op.execute(f"ALTER TABLE {tbl} ALTER COLUMN occurred_at SET NOT NULL")

    # 4) 建索引（若不存在）
    for tbl in ("event_log", "event_error_log"):
        op.execute(
            f"""
            CREATE INDEX IF NOT EXISTS ix_{tbl}_occurred_at
                ON {tbl} (occurred_at)
            """
        )


def downgrade():
    """回滚：必须先删除依赖视图，再删除索引与列（幂等、安全）"""
    conn = op.get_bind()

    # 0) 先删依赖视图（视图依赖 event_error_log.occurred_at）
    #    - v_scan_errors_recent
    #    - v_event_errors_pending
    conn.execute(sa.text(
        """
        DO $$
        BEGIN
          IF to_regclass('public.v_scan_errors_recent') IS NOT NULL THEN
            EXECUTE 'DROP VIEW IF EXISTS public.v_scan_errors_recent';
          END IF;
          IF to_regclass('public.v_event_errors_pending') IS NOT NULL THEN
            EXECUTE 'DROP VIEW IF EXISTS public.v_event_errors_pending';
          END IF;
        END$$;
        """
    ))

    # 1) 删索引（若存在）
    for tbl in ("event_log", "event_error_log"):
        conn.execute(sa.text(f"DROP INDEX IF EXISTS public.ix_{tbl}_occurred_at"))

    # 2) 删列（若存在）
    for tbl in ("event_log", "event_error_log"):
        conn.execute(sa.text(f"""
        DO $$
        BEGIN
          IF to_regclass('public.{tbl}') IS NOT NULL THEN
            IF EXISTS (
              SELECT 1 FROM information_schema.columns
               WHERE table_schema='public'
                 AND table_name='{tbl}'
                 AND column_name='occurred_at'
            ) THEN
              EXECUTE 'ALTER TABLE public.{tbl} DROP COLUMN IF EXISTS occurred_at';
            END IF;
          END IF;
        END$$;
        """))
