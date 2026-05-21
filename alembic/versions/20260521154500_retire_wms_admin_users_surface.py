"""retire_wms_admin_users_surface

Revision ID: 20260521154500_retire_wms_admin_users_surface
Revises: 20260519114500_retire_wms_iam_snapshot
Create Date: 2026-05-21 15:45:00.000000

WMS local user-management UI/API surface has moved to ERP.

This migration retires only the WMS navigation/page route surface:
- page_route_prefixes: /admin/users
- page_registry: admin.users, admin

It intentionally does not delete:
- users
- permissions
- user_permissions
- /users/login
- /users/me
- /users/me/navigation
- /system/write/v1/iam
- /system/sso/v1/exchange

WMS still keeps local users and user_permissions as runtime execution tables.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260521154500_retire_wms_admin_users_surface"
down_revision: Union[str, Sequence[str], None] = "20260519114500_retire_wms_iam_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Retire WMS local admin users page surface."""

    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix = '/admin/users'
           OR page_code = 'admin.users'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'admin.users'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'admin'
          AND NOT EXISTS (
            SELECT 1
            FROM page_registry child
            WHERE child.parent_code = 'admin'
          )
        """
    )


def downgrade() -> None:
    """Restore WMS local admin users page surface."""

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
          'admin',
          '系统管理',
          NULL,
          1,
          'admin',
          FALSE,
          TRUE,
          FALSE,
          (SELECT id FROM permissions WHERE name = 'page.admin.read'),
          (SELECT id FROM permissions WHERE name = 'page.admin.write'),
          900,
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
          'admin.users',
          '用户管理',
          'admin',
          2,
          'admin',
          FALSE,
          TRUE,
          TRUE,
          NULL,
          NULL,
          10,
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
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES (
          '/admin/users',
          'admin.users',
          0,
          TRUE
        )
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )
