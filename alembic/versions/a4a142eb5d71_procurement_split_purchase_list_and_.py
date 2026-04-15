"""procurement split purchase list and create page

Revision ID: a4a142eb5d71
Revises: b0177867937a
Create Date: 2026-04-15 15:14:54.053862

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a4a142eb5d71"
down_revision: Union[str, Sequence[str], None] = "b0177867937a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.execute(
        """
        UPDATE page_registry
        SET name = '采购列表'
        WHERE code = 'procurement.purchase_orders'
        """
    )

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
          'procurement.purchase_orders_new',
          '新建采购单',
          'procurement',
          2,
          'procurement',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          20,
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
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/purchase-orders/overview',
          '/purchase-orders/new-v2',
          '/purchase-orders/' || chr(58) || 'poId'
        )
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
        VALUES
          ('procurement.purchase_orders', '/purchase-orders', 20, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
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
        VALUES
          ('procurement.purchase_orders_new', '/purchase-orders/new', 21, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix = '/purchase-orders/new'
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
        VALUES
          ('procurement.purchase_orders', '/purchase-orders/overview', 21, TRUE),
          ('procurement.purchase_orders', '/purchase-orders/new-v2', 22, TRUE),
          ('procurement.purchase_orders', '/purchase-orders/' || chr(58) || 'poId', 23, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    op.execute(
        """
        UPDATE page_registry
        SET name = '采购单'
        WHERE code = 'procurement.purchase_orders'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'procurement.purchase_orders_new'
        """
    )
