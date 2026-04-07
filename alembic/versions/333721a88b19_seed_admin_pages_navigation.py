"""seed_admin_pages_navigation

Revision ID: 333721a88b19
Revises: 4e00dcea9213
Create Date: 2026-04-06 19:50:46.187540

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "333721a88b19"
down_revision: Union[str, Sequence[str], None] = "4e00dcea9213"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 扩 page_registry.domain_code，纳入 admin
    op.drop_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        type_="check",
    )
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        "domain_code IN ('oms', 'pms', 'procurement', 'wms', 'tms', 'admin')",
    )

    # 2) 新增一级页面权限：page.admin.read / page.admin.write
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.admin.read'),
          ('page.admin.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 3) 新增 / 更新页面注册
    # 当前总原则保持不变：
    # - 一级页面 = 权限主边界
    # - 二级页面 = 展示与归属主边界
    # - admin.users / admin.permissions 继承 admin 权限
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
        VALUES
          (
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
          ),
          (
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
          ),
          (
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

    # 4) 新增 / 更新 route_prefix -> 二级页面映射
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('admin.users', '/admin/users', 0, TRUE),
          ('admin.permissions', '/admin/permissions', 1, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 5) 旧管理权限回填到新的一级页面权限
    # 注意：仍然只回填一级页权限，不给二级页单独 page 权限
    op.execute(
        """
        WITH legacy_admin_users AS (
          SELECT DISTINCT up.user_id
          FROM user_permissions up
          JOIN permissions p
            ON p.id = up.permission_id
          WHERE p.name IN ('system.user.manage', 'system.permission.manage')
        ),
        target_permissions AS (
          SELECT id
          FROM permissions
          WHERE name IN ('page.admin.read', 'page.admin.write')
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT lau.user_id, tp.id
        FROM legacy_admin_users lau
        CROSS JOIN target_permissions tp
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 删除用户上的新 page 权限回填
    op.execute(
        """
        DELETE FROM user_permissions up
        USING permissions p
        WHERE up.permission_id = p.id
          AND p.name IN ('page.admin.read', 'page.admin.write')
        """
    )

    # 2) 删除 route_prefix
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN ('/admin/users', '/admin/permissions')
        """
    )

    # 3) 删除页面
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN ('admin.users', 'admin.permissions', 'admin')
        """
    )

    # 4) 删除权限定义
    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN ('page.admin.read', 'page.admin.write')
        """
    )

    # 5) 收回 domain_code 中的 admin
    op.drop_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        type_="check",
    )
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        "domain_code IN ('oms', 'pms', 'procurement', 'wms', 'tms')",
    )
