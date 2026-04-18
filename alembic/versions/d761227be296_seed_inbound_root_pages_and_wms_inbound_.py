"""seed inbound root pages and wms inbound operations navigation

Revision ID: d761227be296
Revises: 0e6706881685
Create Date: 2026-04-17 19:58:59.730708

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d761227be296"
down_revision: Union[str, Sequence[str], None] = "0e6706881685"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 扩 page_registry.domain_code，纳入 inbound 独立模块
    op.execute(
        """
        ALTER TABLE page_registry
        DROP CONSTRAINT IF EXISTS ck_page_registry_domain_code
        """
    )
    op.execute(
        """
        ALTER TABLE page_registry
        ADD CONSTRAINT ck_page_registry_domain_code
        CHECK (
          domain_code IN (
            'analytics',
            'oms',
            'pms',
            'procurement',
            'wms',
            'tms',
            'admin',
            'inbound'
          )
        )
        """
    )

    # 2) 新增 inbound 一级页权限
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.inbound.read'),
          ('page.inbound.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 3) 过渡期权限回填：
    #    当前已有 page.wms.* 的用户，补发 page.inbound.*，避免新模块上线后不可见
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.wms.read' AS source_name, 'page.inbound.read' AS target_name
          UNION ALL
          SELECT 'page.wms.write', 'page.inbound.write'
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

    # 4) 新增 inbound 一级页
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
          'inbound',
          '入库单据',
          NULL,
          1,
          'inbound',
          TRUE,
          FALSE,
          FALSE,
          (SELECT id FROM permissions WHERE name = 'page.inbound.read'),
          (SELECT id FROM permissions WHERE name = 'page.inbound.write'),
          26,
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

    # 5) 新增 inbound 二级页：汇总 / 采购 / 退货 / 手动
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
            'inbound.summary',
            '入库单汇总',
            'inbound',
            2,
            'inbound',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'inbound.purchase',
            '采购入库单',
            'inbound',
            2,
            'inbound',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'inbound.returns',
            '退货入库单',
            'inbound',
            2,
            'inbound',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            30,
            TRUE
          ),
          (
            'inbound.manual',
            '手动入库单',
            'inbound',
            2,
            'inbound',
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

    # 6) WMS 入库树下新增“收货操作”页
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
          'wms.inbound.operations',
          '收货作业',
          'wms.inbound',
          3,
          'wms',
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

    # 7) 补 route_prefix：
    #    - 入库单详情先挂到 inbound.summary，保持二级页高亮稳定
    #    - WMS 收货操作按 receiptNo 路径进入
    #    - 动态段里的冒号必须写成 \\:param，避免被 SQLAlchemy 当绑定参数解析
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('inbound.summary', '/inbound-receipts', 10, TRUE),
          ('inbound.summary', '/inbound-receipts/\\:receiptId', 11, TRUE),
          ('inbound.purchase', '/inbound-receipts/purchase', 20, TRUE),
          ('inbound.returns', '/inbound-receipts/returns', 30, TRUE),
          ('inbound.manual', '/inbound-receipts/manual', 40, TRUE),
          ('wms.inbound.operations', '/receiving', 40, TRUE),
          ('wms.inbound.operations', '/receiving/\\:receiptNo', 41, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 先删本次新增页面。
    #    page_route_prefixes.page_code -> page_registry.code 是 ON DELETE CASCADE，
    #    所以对应 route_prefix 会自动删除。
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'wms.inbound.operations'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'inbound.summary',
          'inbound.purchase',
          'inbound.returns',
          'inbound.manual'
        )
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'inbound'
        """
    )

    # 2) 删除 inbound 权限定义。
    #    user_permissions.permission_id -> permissions.id 是 ON DELETE CASCADE，
    #    用户上的 page.inbound.* 残留会自动清掉。
    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.inbound.read',
          'page.inbound.write'
        )
        """
    )

    # 3) 恢复 page_registry.domain_code 约束，移除 inbound
    op.execute(
        """
        ALTER TABLE page_registry
        DROP CONSTRAINT IF EXISTS ck_page_registry_domain_code
        """
    )
    op.execute(
        """
        ALTER TABLE page_registry
        ADD CONSTRAINT ck_page_registry_domain_code
        CHECK (
          domain_code IN (
            'analytics',
            'oms',
            'pms',
            'procurement',
            'wms',
            'tms',
            'admin'
          )
        )
        """
    )
