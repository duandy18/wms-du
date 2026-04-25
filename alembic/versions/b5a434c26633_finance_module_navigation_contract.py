"""finance_module_navigation_contract

Revision ID: b5a434c26633
Revises: 78d6f7109582
Create Date: auto

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b5a434c26633'
down_revision: Union[str, Sequence[str], None] = '78d6f7109582'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # page_registry 原约束不允许 finance；先放开，删旧 analytics 节点后再加终态约束。
    op.drop_constraint("ck_page_registry_domain_code", "page_registry", type_="check")

    # 1) 新 finance 权限
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.finance.read'),
          ('page.finance.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 2) 迁移旧 analytics/report 财务权限到 page.finance.*
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.analytics.read' AS source_name, 'page.finance.read' AS target_name
          UNION ALL
          SELECT 'page.analytics.write', 'page.finance.write'
          UNION ALL
          SELECT 'report.finance', 'page.finance.read'
        ),
        pairs AS (
          SELECT DISTINCT
            up.user_id AS user_id,
            tp.id AS permission_id
          FROM mappings m
          JOIN permissions sp ON sp.name = m.source_name
          JOIN user_permissions up ON up.permission_id = sp.id
          JOIN permissions tp ON tp.name = m.target_name
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT user_id, permission_id
        FROM pairs
        ON CONFLICT (user_id, permission_id) DO NOTHING
        """
    )

    # 3) 退旧 finance/analytics 运行态 route
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/finance',
          '/finance/overview',
          '/finance/overview/daily',
          '/finance/shop',
          '/finance/sku',
          '/finance/order-unit'
        )
           OR page_code IN (
             'analytics',
             'analytics.finance',
             'wms.analytics.finance'
           )
        """
    )

    # 4) 先删子页，再删旧 root
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN ('analytics.finance', 'wms.analytics.finance')
        """
    )
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'analytics'
        """
    )

    # 5) 新 finance root
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
          'finance',
          '财务分析',
          NULL,
          1,
          'finance',
          TRUE,
          FALSE,
          FALSE,
          (SELECT id FROM permissions WHERE name = 'page.finance.read'),
          (SELECT id FROM permissions WHERE name = 'page.finance.write'),
          70,
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

    # 6) 新 finance 二级页
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
          ('finance.overview', '综合分析', 'finance', 2, 'finance', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE),
          ('finance.order_sales', '订单销售', 'finance', 2, 'finance', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE),
          ('finance.purchase_cost', '采购成本', 'finance', 2, 'finance', FALSE, TRUE, TRUE, NULL, NULL, 30, TRUE),
          ('finance.shipping_cost', '物流成本', 'finance', 2, 'finance', FALSE, TRUE, TRUE, NULL, NULL, 40, TRUE)
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

    # 7) 终态 route_prefixes：不保留旧页面 route
    op.execute(
        """
        INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
        VALUES
          ('/finance', 'finance.overview', 10, TRUE),
          ('/finance/order-sales', 'finance.order_sales', 20, TRUE),
          ('/finance/purchase-costs', 'finance.purchase_cost', 30, TRUE),
          ('/finance/shipping-costs', 'finance.shipping_cost', 40, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 8) 删旧权限字典项；user_permissions 会级联清理旧权限残留。
    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.analytics.read',
          'page.analytics.write',
          'report.finance'
        )
        """
    )

    # 9) 加终态 domain_code 约束：finance 替代 analytics。
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        "domain_code IN ('finance', 'oms', 'pms', 'procurement', 'wms', 'shipping_assist', 'admin', 'inbound')",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint("ck_page_registry_domain_code", "page_registry", type_="check")

    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.analytics.read'),
          ('page.analytics.write'),
          ('report.finance')
        ON CONFLICT (name) DO NOTHING
        """
    )

    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.finance.read' AS source_name, 'page.analytics.read' AS target_name
          UNION ALL
          SELECT 'page.finance.write', 'page.analytics.write'
          UNION ALL
          SELECT 'page.finance.read', 'report.finance'
        ),
        pairs AS (
          SELECT DISTINCT
            up.user_id AS user_id,
            tp.id AS permission_id
          FROM mappings m
          JOIN permissions sp ON sp.name = m.source_name
          JOIN user_permissions up ON up.permission_id = sp.id
          JOIN permissions tp ON tp.name = m.target_name
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT user_id, permission_id
        FROM pairs
        ON CONFLICT (user_id, permission_id) DO NOTHING
        """
    )

    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/finance',
          '/finance/order-sales',
          '/finance/purchase-costs',
          '/finance/shipping-costs'
        )
           OR page_code LIKE 'finance.%'
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'finance.overview',
          'finance.order_sales',
          'finance.purchase_cost',
          'finance.shipping_cost'
        )
        """
    )
    op.execute("DELETE FROM page_registry WHERE code = 'finance'")

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
          'wms.analytics.finance',
          '财务分析',
          'analytics',
          2,
          'analytics',
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
        INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
        VALUES ('/finance', 'wms.analytics.finance', 10, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.finance.read',
          'page.finance.write'
        )
        """
    )

    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        "domain_code IN ('analytics', 'oms', 'pms', 'procurement', 'wms', 'shipping_assist', 'admin', 'inbound')",
    )
