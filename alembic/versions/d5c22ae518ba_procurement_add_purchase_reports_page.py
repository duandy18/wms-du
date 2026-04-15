# alembic/versions/d5c22ae518ba_procurement_add_purchase_reports_page.py
"""procurement add purchase reports page

Revision ID: d5c22ae518ba
Revises: a23dfdafced7
Create Date: 2026-04-15 20:54:17.166403

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d5c22ae518ba"
down_revision: Union[str, Sequence[str], None] = "a23dfdafced7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

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
          'procurement.purchase_reports',
          '采购报表',
          'procurement',
          2,
          'procurement',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          40,
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
          'procurement.purchase_reports',
          '/purchase-reports',
          40,
          TRUE
        )
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
        WHERE route_prefix = '/purchase-reports'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'procurement.purchase_reports'
        """
    )
