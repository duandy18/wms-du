"""recreate v_scan_recent with JSONB-safe COALESCE(ref/scan_ref/text)

Revision ID: 20251104_v_scan_recent_jsonb_coalesce
Revises: 20251104_v_scan_trace_jsonb_coalesce
Create Date: 2025-11-04 16:30:00
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "20251104_v_scan_recent_jsonb_coalesce"
down_revision = "20251104_v_scan_trace_jsonb_coalesce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    将 v_scan_recent 重建为 JSONB 兼容视图：
      - commit 事件（JSON 对象）优先读 message->>'ref' / message->>'scan_ref'
      - probe 事件（字符串）回退为 btrim(message::text,'"')
      - 最近 500 条扫描事件，按 occurred_at DESC
    """
    op.execute(
        text("""
    CREATE OR REPLACE VIEW public.v_scan_recent AS
    SELECT
        e.id           AS event_id,
        e.source,
        e.occurred_at,
        e.message      AS message_raw,
        COALESCE(
            e.message->>'ref',
            e.message->>'scan_ref',
            btrim(e.message::text, '"')
        )              AS scan_ref
    FROM public.event_log e
    WHERE e.source LIKE 'scan_%'
    ORDER BY e.occurred_at DESC
    LIMIT 500;
    """)
    )


def downgrade() -> None:
    """
    回滚：删除该视图（如需恢复旧版定义，可在此放回旧版 CREATE VIEW）。
    """
    op.execute(text("DROP VIEW IF EXISTS public.v_scan_recent;"))
