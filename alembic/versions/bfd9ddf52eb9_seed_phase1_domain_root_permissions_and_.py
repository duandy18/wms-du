"""seed phase1 domain root permissions and pages

Revision ID: bfd9ddf52eb9
Revises: 43f4fd19527e
Create Date: 2026-04-07 11:41:08.573720

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "bfd9ddf52eb9"
down_revision: Union[str, Sequence[str], None] = "43f4fd19527e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 新增 phase1 领域一级页权限
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.analytics.read'),
          ('page.analytics.write'),
          ('page.oms.read'),
          ('page.oms.write'),
          ('page.tms.read'),
          ('page.tms.write'),
          ('page.pms.read'),
          ('page.pms.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 2) 新增 / 更新一级页面注册
    # 当前阶段：
    # - 只建立新的一级领域页
    # - 不改挂二级页
    # - 不处理 route_prefix
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
            'oms',
            '订单管理',
            NULL,
            1,
            'oms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.oms.read'),
            (SELECT id FROM permissions WHERE name = 'page.oms.write'),
            30,
            TRUE
          ),
          (
            'tms',
            '物流',
            NULL,
            1,
            'tms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.tms.read'),
            (SELECT id FROM permissions WHERE name = 'page.tms.write'),
            40,
            TRUE
          ),
          (
            'analytics',
            '数据分析',
            NULL,
            1,
            'analytics',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.analytics.read'),
            (SELECT id FROM permissions WHERE name = 'page.analytics.write'),
            70,
            TRUE
          ),
          (
            'pms',
            '商品主数据',
            NULL,
            1,
            'pms',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.pms.read'),
            (SELECT id FROM permissions WHERE name = 'page.pms.write'),
            80,
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

    # 先删一级页面，再删权限定义
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN ('analytics', 'oms', 'tms', 'pms')
        """
    )

    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.analytics.read',
          'page.analytics.write',
          'page.oms.read',
          'page.oms.write',
          'page.tms.read',
          'page.tms.write',
          'page.pms.read',
          'page.pms.write'
        )
        """
    )
