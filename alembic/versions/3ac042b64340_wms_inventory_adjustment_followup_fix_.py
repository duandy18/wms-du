"""wms_inventory_adjustment_followup_fix_inbound_manual_navigation

Revision ID: 3ac042b64340
Revises: e39546a3ae97
Create Date: 2026-04-21 18:07:00.940183

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3ac042b64340"
down_revision: Union[str, Sequence[str], None] = "e39546a3ae97"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 补齐 WMS 入库树缺失的手动收货页
    op.execute(
        """
        INSERT INTO page_registry (
          code,
          name,
          parent_code,
          level,
          domain_code,
          show_in_topbar,
          show_in_sidebar,
          inherit_permissions,
          read_permission_id,
          write_permission_id,
          sort_order,
          is_active
        )
        VALUES (
          'wms.inbound.manual',
          '手动收货',
          'wms.inbound',
          3,
          'wms',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          30,
          TRUE
        )
        ON CONFLICT (code) DO UPDATE
        SET
          name = EXCLUDED.name,
          parent_code = EXCLUDED.parent_code,
          level = EXCLUDED.level,
          domain_code = EXCLUDED.domain_code,
          show_in_topbar = EXCLUDED.show_in_topbar,
          show_in_sidebar = EXCLUDED.show_in_sidebar,
          inherit_permissions = EXCLUDED.inherit_permissions,
          read_permission_id = EXCLUDED.read_permission_id,
          write_permission_id = EXCLUDED.write_permission_id,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 2) 补齐手动收货路由归属
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES (
          'wms.inbound.manual',
          '/receiving/manual',
          30,
          TRUE
        )
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 3) 再次收正历史残留：
    #    operations 不是当前可见导航页，且若历史前缀误挂到它，统一改挂 atomic
    op.execute(
        """
        UPDATE page_route_prefixes
           SET page_code = 'wms.inbound.atomic'
         WHERE page_code = 'wms.inbound.operations'
        """
    )

    op.execute(
        """
        UPDATE page_registry
           SET is_active = FALSE
         WHERE code = 'wms.inbound.operations'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    raise RuntimeError(
        "Downgrade not supported: inventory adjustment navigation cutover follow-up is intentionally one-way."
    )
