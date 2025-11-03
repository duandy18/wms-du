"""recreate v_scan_trace with JSONB-safe COALESCE(ref/scan_ref/text)

Revision ID: 20251104_v_scan_trace_jsonb_coalesce
Revises: ed9ef423378f
Create Date: 2025-11-04 14:30:00
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20251104_v_scan_trace_jsonb_coalesce"
down_revision = "ed9ef423378f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    将 v_scan_trace 重建为 JSONB 兼容版：
      - commit 事件（JSON 对象）优先读取 message->>'ref' / message->>'scan_ref'
      - probe 事件（字符串）回退为 btrim(message::text, '"')
      - JOIN stock_ledger 时也使用同样的规范化，确保能联到 commit 对应腿
    """
    op.execute(text("""
    CREATE OR REPLACE VIEW public.v_scan_trace AS
    SELECT
        e.id           AS event_id,
        e.source,
        e.occurred_at,
        e.message      AS message_raw,
        COALESCE(
            e.message->>'ref',
            e.message->>'scan_ref',
            btrim(e.message::text, '"')
        )              AS scan_ref,
        l.id           AS ledger_id,
        l.reason,
        l.item_id,
        l.location_id,
        l.delta
    FROM public.event_log e
    LEFT JOIN public.stock_ledger l
      ON l.ref::text = COALESCE(
            e.message->>'ref',
            e.message->>'scan_ref',
            btrim(e.message::text, '"')
         )
    WHERE e.source LIKE 'scan_%';
    """))


def downgrade() -> None:
    """
    回滚：仅删除该视图。
    若需恢复旧版定义，可在此处补充旧版 CREATE VIEW 语句。
    """
    op.execute(text("DROP VIEW IF EXISTS public.v_scan_trace;"))
