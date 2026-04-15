"""seed procurement root page and rebind purchase order routes

Revision ID: 5028e6e55b24
Revises: 65012e944c84
Create Date: 2026-04-13 13:55:03.134955

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5028e6e55b24"
down_revision: Union[str, Sequence[str], None] = "65012e944c84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 新增 procurement 一级页权限
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.procurement.read'),
          ('page.procurement.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 2) 新增 / 更新 procurement 一级页
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
          'procurement',
          '采购管理',
          NULL,
          1,
          'procurement',
          TRUE,
          FALSE,
          FALSE,
          (SELECT id FROM permissions WHERE name = 'page.procurement.read'),
          (SELECT id FROM permissions WHERE name = 'page.procurement.write'),
          25,
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

    # 3) 新增 / 更新 procurement 二级页
    # 当前先只建立一个“采购单”页面组，不在这一步继续拆 completion 独立页。
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
          'procurement.purchase_orders',
          '采购单',
          'procurement',
          2,
          'procurement',
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

    # 4) 采购计划相关 route_prefix 改挂到 procurement.purchase_orders
    # 注意：
    # - 这里只搬 purchase-orders*，不搬 /receive-tasks/:taskId
    # - 动态段里的冒号需要写成 \\:xxx，避免被 SQLAlchemy 当绑定参数解析
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('procurement.purchase_orders', '/purchase-orders', 20, TRUE),
          ('procurement.purchase_orders', '/purchase-orders/overview', 21, TRUE),
          ('procurement.purchase_orders', '/purchase-orders/new-v2', 22, TRUE),
          ('procurement.purchase_orders', '/purchase-orders/\\:poId', 23, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 5) 过渡期回填：
    # 当前采购页前端仍是 page.wms.read/page.wms.write 守卫；
    # 为避免切页后把现有可访问用户锁死，这里把 WMS 一级页权限补发到 procurement 一级页权限。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.wms.read' AS source_name, 'page.procurement.read' AS target_name
          UNION ALL
          SELECT 'page.wms.write', 'page.procurement.write'
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


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 先把 purchase-orders* 路由挂回 WMS 入库采购页
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('wms.inbound.purchase', '/purchase-orders', 20, TRUE),
          ('wms.inbound.purchase', '/purchase-orders/overview', 21, TRUE),
          ('wms.inbound.purchase', '/purchase-orders/new-v2', 22, TRUE),
          ('wms.inbound.purchase', '/purchase-orders/\\:poId', 23, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 2) 删除 procurement 二级页
    # route_prefixes.page_code -> page_registry.code 是 ON DELETE CASCADE；
    # 但上一步已把 purchase-orders* 路由改挂回 wms.inbound.purchase，这里不会误删这些路由。
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'procurement.purchase_orders'
        """
    )

    # 3) 删除 procurement 一级页
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'procurement'
        """
    )

    # 4) 删除 procurement 权限定义
    # user_permissions.permission_id -> permissions.id 是 ON DELETE CASCADE，
    # 用户上的 page.procurement.* 残留会自动清掉。
    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.procurement.read',
          'page.procurement.write'
        )
        """
    )
