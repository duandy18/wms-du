"""merge heads: v_scan_trace_jsonb_coalesce + v_scan_recent_jsonb_coalesce

Revision ID: 20251104_merge_scan_views_heads
Revises: 20251104_v_scan_trace_jsonb_coalesce, 20251104_v_scan_recent_jsonb_coalesce
Create Date: 2025-11-04 17:45:00
"""

from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "20251104_merge_scan_views_heads"
down_revision: Union[str, Sequence[str], None] = (
    "20251104_v_scan_trace_jsonb_coalesce",
    "20251104_v_scan_recent_jsonb_coalesce",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # no-op: merge only
    pass


def downgrade() -> None:
    # no-op: cannot split heads
    pass
