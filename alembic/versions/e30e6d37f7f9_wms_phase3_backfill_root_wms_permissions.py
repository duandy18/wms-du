"""wms_phase3_backfill_root_wms_permissions

Revision ID: e30e6d37f7f9
Revises: f95f00c3360f
Create Date: 2026-04-07 17:42:21.364293

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e30e6d37f7f9"
down_revision: Union[str, Sequence[str], None] = "f95f00c3360f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 把旧 WMS 一级页权限补发到新的 WMS 根权限。
    # 这里只补发，不删除旧权限。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.wms.inbound.read' AS source_name, 'page.wms.read' AS target_name
          UNION ALL
          SELECT 'page.wms.inbound.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.inventory.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.inventory.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.order_outbound.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.order_outbound.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.internal_ops.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.internal_ops.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.masterdata.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.masterdata.write', 'page.wms.write'
        ),
        pairs AS (
          SELECT DISTINCT
            up.user_id AS user_id,
            tp.id AS permission_id
          FROM mappings m
          JOIN permissions sp
            ON sp.name = m.source_name
          JOIN user_permissions up
            ON up.permission_id = sp.id
          JOIN permissions tp
            ON tp.name = m.target_name
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT user_id, permission_id
        FROM pairs
        ON CONFLICT (user_id, permission_id) DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 撤回本次补发的新 WMS 根权限。
    # 只删除“当前仍拥有对应旧 WMS 一级页权限”的用户上的 root 权限，避免过度删除。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.wms.inbound.read' AS source_name, 'page.wms.read' AS target_name
          UNION ALL
          SELECT 'page.wms.inbound.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.inventory.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.inventory.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.order_outbound.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.order_outbound.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.internal_ops.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.internal_ops.write', 'page.wms.write'
          UNION ALL
          SELECT 'page.wms.masterdata.read', 'page.wms.read'
          UNION ALL
          SELECT 'page.wms.masterdata.write', 'page.wms.write'
        )
        DELETE FROM user_permissions up
        USING mappings m, permissions tp, permissions sp, user_permissions old_up
        WHERE up.permission_id = tp.id
          AND tp.name = m.target_name
          AND sp.name = m.source_name
          AND old_up.permission_id = sp.id
          AND old_up.user_id = up.user_id
        """
    )
