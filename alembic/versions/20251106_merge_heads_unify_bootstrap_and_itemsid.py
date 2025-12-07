"""merge heads: unify items_id_identity and bootstrap_stage_location_and_ids

Revision ID: 20251106_merge_heads_unify_bootstrap_and_itemsid
Revises: 20251106_items_id_identity, 20251106_bootstrap_stage_location_and_ids
Create Date: 2025-11-06 16:35:00+08
"""

# 注意：这是一个 MERGE 迁移，用于把两条 head 合并为单一 head。
# 不做任何 schema 变更，仅用于收束迁移链。

revision = "20251106_merge_heads_unify_bootstrap_and_itemsid"
down_revision = ("20251106_items_id_identity", "20251106_bootstrap_stage_location_and_ids")
branch_labels = None
depends_on = None


def upgrade():
    # no-op: just a merge point
    pass


def downgrade():
    # 退回到两个并行 head（通常不需要执行）
    pass
