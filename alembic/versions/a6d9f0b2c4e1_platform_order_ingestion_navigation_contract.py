"""platform_order_ingestion_navigation_contract

Revision ID: a6d9f0b2c4e1
Revises: 9b8c7d6e5f4a
Create Date: 2026-04-27 16:20:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "a6d9f0b2c4e1"
down_revision: Union[str, Sequence[str], None] = "9b8c7d6e5f4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOMAIN_CHECK_WITH_PLATFORM_ORDER_INGESTION = (
    "domain_code IN ("
    "'finance', "
    "'oms', "
    "'pms', "
    "'procurement', "
    "'wms', "
    "'shipping_assist', "
    "'admin', "
    "'inbound', "
    "'platform_order_ingestion'"
    ")"
)

DOMAIN_CHECK_WITHOUT_PLATFORM_ORDER_INGESTION = (
    "domain_code IN ("
    "'finance', "
    "'oms', "
    "'pms', "
    "'procurement', "
    "'wms', "
    "'shipping_assist', "
    "'admin', "
    "'inbound'"
    ")"
)

LEGACY_OMS_PLATFORM_ROUTE_PREFIXES = (
    "/oms/pdd/stores",
    "/oms/pdd/orders",
    "/oms/taobao/stores",
    "/oms/taobao/orders",
    "/oms/jd/stores",
    "/oms/jd/orders",
)

LEGACY_OMS_PLATFORM_PAGE_CODES = (
    "wms.order_management.pdd_stores",
    "wms.order_management.pdd_orders",
    "wms.order_management.taobao_stores",
    "wms.order_management.taobao_orders",
    "wms.order_management.jd_stores",
    "wms.order_management.jd_orders",
)

PLATFORM_ORDER_INGESTION_PAGE_CODES_BOTTOM_UP = (
    "platform_order_ingestion.pdd.collect",
    "platform_order_ingestion.pdd.native_orders",
    "platform_order_ingestion.taobao.collect",
    "platform_order_ingestion.taobao.native_orders",
    "platform_order_ingestion.jd.collect",
    "platform_order_ingestion.jd.native_orders",
    "platform_order_ingestion.overview",
    "platform_order_ingestion.pdd",
    "platform_order_ingestion.taobao",
    "platform_order_ingestion.jd",
    "platform_order_ingestion",
)

PLATFORM_ORDER_INGESTION_ROUTE_PREFIXES = (
    "/platform-order-ingestion",
    "/platform-order-ingestion/pdd/collect",
    "/platform-order-ingestion/pdd/native-orders",
    "/platform-order-ingestion/taobao/collect",
    "/platform-order-ingestion/taobao/native-orders",
    "/platform-order-ingestion/jd/collect",
    "/platform-order-ingestion/jd/native-orders",
)


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 扩 domain_code 约束，纳入平台订单采集独立模块。
    op.drop_constraint("ck_page_registry_domain_code", "page_registry", type_="check")
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        DOMAIN_CHECK_WITH_PLATFORM_ORDER_INGESTION,
    )

    # 2) 新增独立页面权限。
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES
          ('page.platform_order_ingestion.read'),
          ('page.platform_order_ingestion.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # 3) 从旧 OMS 页面权限补发到新平台订单采集权限。
    #    这是一次性切换，不保留双入口；已有 OMS 授权用户不会因为导航拆分丢访问权。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.oms.read' AS source_name,
                 'page.platform_order_ingestion.read' AS target_name
          UNION ALL
          SELECT 'page.oms.write',
                 'page.platform_order_ingestion.write'
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

    # 4) 先移除旧 OMS 下平台店铺/订单导航 route_prefix。
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/oms/pdd/stores',
          '/oms/pdd/orders',
          '/oms/taobao/stores',
          '/oms/taobao/orders',
          '/oms/jd/stores',
          '/oms/jd/orders'
        )
           OR page_code IN (
          'wms.order_management.pdd_stores',
          'wms.order_management.pdd_orders',
          'wms.order_management.taobao_stores',
          'wms.order_management.taobao_orders',
          'wms.order_management.jd_stores',
          'wms.order_management.jd_orders'
        )
        """
    )

    # 5) 删除旧 OMS 下平台店铺/订单页面节点。
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.order_management.pdd_stores',
          'wms.order_management.pdd_orders',
          'wms.order_management.taobao_stores',
          'wms.order_management.taobao_orders',
          'wms.order_management.jd_stores',
          'wms.order_management.jd_orders'
        )
        """
    )

    # 6) 禁用空壳 OMS 根页面。
    #    OMS 后续做 FSKU 映射/内部订单时，可由新的专门迁移重新启用和挂载终态页面。
    op.execute(
        """
        UPDATE page_registry
           SET is_active = FALSE
         WHERE code = 'oms'
        """
    )

    # 7) 新增平台订单采集三级页面树。
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
            'platform_order_ingestion',
            '平台订单采集',
            NULL,
            1,
            'platform_order_ingestion',
            TRUE,
            FALSE,
            FALSE,
            (SELECT id FROM permissions WHERE name = 'page.platform_order_ingestion.read'),
            (SELECT id FROM permissions WHERE name = 'page.platform_order_ingestion.write'),
            30,
            TRUE
          ),
          (
            'platform_order_ingestion.overview',
            '采集总览',
            'platform_order_ingestion',
            2,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'platform_order_ingestion.pdd',
            '拼多多',
            'platform_order_ingestion',
            2,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'platform_order_ingestion.taobao',
            '淘宝',
            'platform_order_ingestion',
            2,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            30,
            TRUE
          ),
          (
            'platform_order_ingestion.jd',
            '京东',
            'platform_order_ingestion',
            2,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            40,
            TRUE
          ),
          (
            'platform_order_ingestion.pdd.collect',
            '拼多多订单采集',
            'platform_order_ingestion.pdd',
            3,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'platform_order_ingestion.pdd.native_orders',
            '拼多多原生订单台账',
            'platform_order_ingestion.pdd',
            3,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'platform_order_ingestion.taobao.collect',
            '淘宝订单采集',
            'platform_order_ingestion.taobao',
            3,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'platform_order_ingestion.taobao.native_orders',
            '淘宝原生订单台账',
            'platform_order_ingestion.taobao',
            3,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'platform_order_ingestion.jd.collect',
            '京东订单采集',
            'platform_order_ingestion.jd',
            3,
            'platform_order_ingestion',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'platform_order_ingestion.jd.native_orders',
            '京东原生订单台账',
            'platform_order_ingestion.jd',
            3,
            'platform_order_ingestion',
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

    # 8) 终态 route_prefixes。
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES
          (
            '/platform-order-ingestion',
            'platform_order_ingestion.overview',
            10,
            TRUE
          ),
          (
            '/platform-order-ingestion/pdd/collect',
            'platform_order_ingestion.pdd.collect',
            20,
            TRUE
          ),
          (
            '/platform-order-ingestion/pdd/native-orders',
            'platform_order_ingestion.pdd.native_orders',
            30,
            TRUE
          ),
          (
            '/platform-order-ingestion/taobao/collect',
            'platform_order_ingestion.taobao.collect',
            40,
            TRUE
          ),
          (
            '/platform-order-ingestion/taobao/native-orders',
            'platform_order_ingestion.taobao.native_orders',
            50,
            TRUE
          ),
          (
            '/platform-order-ingestion/jd/collect',
            'platform_order_ingestion.jd.collect',
            60,
            TRUE
          ),
          (
            '/platform-order-ingestion/jd/native-orders',
            'platform_order_ingestion.jd.native_orders',
            70,
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

    # 1) 放开约束，先允许清理 platform_order_ingestion 域。
    op.drop_constraint("ck_page_registry_domain_code", "page_registry", type_="check")

    # 2) 回滚时把新权限近似补回 OMS 权限，保证授权可逆。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.platform_order_ingestion.read' AS source_name,
                 'page.oms.read' AS target_name
          UNION ALL
          SELECT 'page.platform_order_ingestion.write',
                 'page.oms.write'
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

    # 3) 删除新 route_prefix。
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/platform-order-ingestion',
          '/platform-order-ingestion/pdd/collect',
          '/platform-order-ingestion/pdd/native-orders',
          '/platform-order-ingestion/taobao/collect',
          '/platform-order-ingestion/taobao/native-orders',
          '/platform-order-ingestion/jd/collect',
          '/platform-order-ingestion/jd/native-orders'
        )
           OR page_code = 'platform_order_ingestion'
           OR page_code LIKE 'platform_order_ingestion.%'
        """
    )

    # 4) 删除新页面树，按子到父顺序，避免 parent_code RESTRICT。
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'platform_order_ingestion.pdd.collect',
          'platform_order_ingestion.pdd.native_orders',
          'platform_order_ingestion.taobao.collect',
          'platform_order_ingestion.taobao.native_orders',
          'platform_order_ingestion.jd.collect',
          'platform_order_ingestion.jd.native_orders'
        )
        """
    )
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'platform_order_ingestion.overview',
          'platform_order_ingestion.pdd',
          'platform_order_ingestion.taobao',
          'platform_order_ingestion.jd'
        )
        """
    )
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'platform_order_ingestion'
        """
    )

    # 5) 恢复 OMS 根页面。
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

    # 6) 恢复旧 OMS 平台店铺/订单页面节点。
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
            'wms.order_management.pdd_stores',
            '拼多多店铺',
            'oms',
            2,
            'oms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'wms.order_management.pdd_orders',
            '拼多多订单',
            'oms',
            2,
            'oms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'wms.order_management.taobao_stores',
            '淘宝店铺',
            'oms',
            2,
            'oms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            30,
            TRUE
          ),
          (
            'wms.order_management.taobao_orders',
            '淘宝订单',
            'oms',
            2,
            'oms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            40,
            TRUE
          ),
          (
            'wms.order_management.jd_stores',
            '京东店铺',
            'oms',
            2,
            'oms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            50,
            TRUE
          ),
          (
            'wms.order_management.jd_orders',
            '京东订单',
            'oms',
            2,
            'oms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            60,
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

    # 7) 恢复旧 route_prefix。
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES
          ('/oms/pdd/stores', 'wms.order_management.pdd_stores', 10, TRUE),
          ('/oms/pdd/orders', 'wms.order_management.pdd_orders', 20, TRUE),
          ('/oms/taobao/stores', 'wms.order_management.taobao_stores', 30, TRUE),
          ('/oms/taobao/orders', 'wms.order_management.taobao_orders', 40, TRUE),
          ('/oms/jd/stores', 'wms.order_management.jd_stores', 50, TRUE),
          ('/oms/jd/orders', 'wms.order_management.jd_orders', 60, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 8) 删除新权限；user_permissions 会级联清理。
    op.execute(
        """
        DELETE FROM permissions
        WHERE name IN (
          'page.platform_order_ingestion.read',
          'page.platform_order_ingestion.write'
        )
        """
    )

    # 9) 恢复原 domain_code 约束。
    op.create_check_constraint(
        "ck_page_registry_domain_code",
        "page_registry",
        DOMAIN_CHECK_WITHOUT_PLATFORM_ORDER_INGESTION,
    )
