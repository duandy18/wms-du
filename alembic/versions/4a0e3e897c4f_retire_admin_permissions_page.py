"""retire_admin_permissions_page

Revision ID: 4a0e3e897c4f
Revises: d62cc07bb5c9
Create Date: 2026-04-08 22:00:52.177404

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4a0e3e897c4f"
down_revision: Union[str, Sequence[str], None] = "d62cc07bb5c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 先删 route_prefix，再删 page_registry，避免外键阻塞
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix = '/admin/permissions'
           OR page_code = 'admin.permissions'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'admin.permissions'
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
          'admin.permissions',
          '权限管理',
          'admin',
          2,
          'admin',
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
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES (
          'admin.permissions',
          '/admin/permissions',
          1,
          TRUE
        )
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
