"""wms_phase3_seed_wms_root_page_and_permissions

Revision ID: f69be92871c7
Revises: 711e3a1495a6
Create Date: 2026-04-07 17:03:34.430262

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f69be92871c7"
down_revision: Union[str, Sequence[str], None] = "711e3a1495a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 新增 WMS 一级页权限
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.wms.read'),
          ('page.wms.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 2) 新增 / 更新 WMS 一级页
    # 当前阶段只建立新的一级根页：
    # - 一级页面 = 权限主边界
    # - 不挂子页
    # - 不处理 route_prefix
    # - 不做旧树退役
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
            'wms',
            '仓储管理',
            NULL,
            1,
            'wms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.wms.read'),
            (SELECT id FROM permissions WHERE name = 'page.wms.write'),
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


def downgrade() -> None:
    """Downgrade schema."""

    # 先删一级页，再删权限定义
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'wms'
        """
    )

    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.wms.read',
          'page.wms.write'
        )
        """
    )
