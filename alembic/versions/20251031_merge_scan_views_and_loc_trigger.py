"""merge heads: unify locations trigger & scan views

Revision ID: 20251031_merge_scan_views_and_loc_trigger
Revises: 20251031_locations_fill_code_trigger, 20251031_scan_event_views
Create Date: 2025-10-31
"""

from alembic import op  # noqa: F401

# -- Merge identifiers --
revision = "20251031_merge_scan_views_and_loc_trigger"
down_revision = (
    "20251031_locations_fill_code_trigger",
    "20251031_scan_event_views",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 纯合并点，不做任何结构改动
    pass


def downgrade() -> None:
    # 回到分叉状态（一般无需执行）
    pass
