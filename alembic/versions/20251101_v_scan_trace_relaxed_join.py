"""v_scan_trace: relaxed join by extracting ref from event_log.message (column-guarded)

Revision ID: 20251101_v_scan_trace_relaxed_join
Revises: 20251031_merge_scan_views_and_loc_trigger
Create Date: 2025-11-01 09:30:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20251101_v_scan_trace_relaxed_join"
down_revision = "20251031_merge_scan_views_and_loc_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 先安全删除旧视图（若存在）
    op.execute("DROP VIEW IF EXISTS public.v_scan_trace CASCADE")

    # 使用列探测 + 动态 SQL：若 stock_ledger 有 location_id，则选择该列；否则用 NULL::int 占位
    op.execute(
        """
        DO $$
        DECLARE
          has_loc bool;
          sql     text;
        BEGIN
          SELECT EXISTS (
            SELECT 1
              FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='stock_ledger'
               AND column_name='location_id'
          ) INTO has_loc;

          IF has_loc THEN
            sql := $v$
              CREATE VIEW public.v_scan_trace AS
              SELECT
                  e.id            AS event_id,
                  e.source        AS source,
                  e.occurred_at   AS occurred_at,
                  e.message       AS message_raw,
                  CASE
                      WHEN e.message IS NOT NULL AND left(e.message, 1) = '{'
                          THEN (e.message::jsonb ->> 'ref')
                      ELSE e.message
                  END             AS scan_ref,
                  l.id            AS ledger_id,
                  l.reason        AS reason,
                  l.item_id       AS item_id,
                  l.location_id   AS location_id,
                  l.delta         AS delta
              FROM public.event_log e
              LEFT JOIN public.stock_ledger l
                     ON l.ref = CASE
                                   WHEN e.message IS NOT NULL AND left(e.message, 1) = '{'
                                       THEN (e.message::jsonb ->> 'ref')
                                   ELSE e.message
                                END
              WHERE e.source LIKE 'scan_%';
            $v$;
          ELSE
            sql := $v$
              CREATE VIEW public.v_scan_trace AS
              SELECT
                  e.id            AS event_id,
                  e.source        AS source,
                  e.occurred_at   AS occurred_at,
                  e.message       AS message_raw,
                  CASE
                      WHEN e.message IS NOT NULL AND left(e.message, 1) = '{'
                          THEN (e.message::jsonb ->> 'ref')
                      ELSE e.message
                  END             AS scan_ref,
                  l.id            AS ledger_id,
                  l.reason        AS reason,
                  l.item_id       AS item_id,
                  NULL::int       AS location_id,
                  l.delta         AS delta
              FROM public.event_log e
              LEFT JOIN public.stock_ledger l
                     ON l.ref = CASE
                                   WHEN e.message IS NOT NULL AND left(e.message, 1) = '{'
                                       THEN (e.message::jsonb ->> 'ref')
                                   ELSE e.message
                                END
              WHERE e.source LIKE 'scan_%';
            $v$;
          END IF;

          EXECUTE sql;
        END$$;
        """
    )


def downgrade() -> None:
    # 回滚时只需删除该视图；具体旧版视图由前一迁移负责
    op.execute("DROP VIEW IF EXISTS public.v_scan_trace CASCADE")
