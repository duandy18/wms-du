"""wms_remove_inventory_adjustment_return_inbound_page

Revision ID: a2ceea372e0e
Revises: 87dfd5118ca6
Create Date: 2026-04-24 12:21:51.722236

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a2ceea372e0e"
down_revision: Union[str, Sequence[str], None] = "87dfd5118ca6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix = '/inventory-adjustment/return-inbound'
           OR page_code = 'wms.inventory_adjustment.return_inbound'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'wms.inventory_adjustment.return_inbound'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
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
          'wms.inventory_adjustment.return_inbound',
          '退单入库',
          'wms.inventory_adjustment',
          3,
          'wms',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          50,
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

    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES (
          'wms.inventory_adjustment.return_inbound',
          '/inventory-adjustment/return-inbound',
          50,
          TRUE
        )
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
