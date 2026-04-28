"""oms_retire_platform_ingestion_register_workflow

Revision ID: 202604281430
Revises: c7a9e1f42b6d
Create Date: 2026-04-28 14:30:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "202604281430"
down_revision: Union[str, Sequence[str], None] = "c7a9e1f42b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_PLATFORM_PAGE_CODES = (
    "platform_order_ingestion.jd.collect",
    "platform_order_ingestion.jd.native_orders",
    "platform_order_ingestion.pdd.collect",
    "platform_order_ingestion.pdd.native_orders",
    "platform_order_ingestion.taobao.collect",
    "platform_order_ingestion.taobao.native_orders",
    "platform_order_ingestion.jd",
    "platform_order_ingestion.pdd",
    "platform_order_ingestion.taobao",
    "platform_order_ingestion.overview",
    "platform_order_ingestion",
)

OLD_PLATFORM_PERMISSION_NAMES = (
    "page.platform_order_ingestion.read",
    "page.platform_order_ingestion.write",
)

OMS_PAGE_ROWS = (
    ("oms", "订单管理", None, 1, "oms", True, False, False, "page.oms.read", "page.oms.write", 30, True),

    ("oms.pdd", "拼多多", "oms", 2, "oms", False, True, True, None, None, 10, True),
    ("oms.pdd.import", "订单导入", "oms.pdd", 3, "oms", False, True, True, None, None, 10, True),
    ("oms.pdd.platform_order_mirror", "平台订单镜像", "oms.pdd", 3, "oms", False, True, True, None, None, 20, True),
    ("oms.pdd.fsku_mapping", "商品映射", "oms.pdd", 3, "oms", False, True, True, None, None, 30, True),
    ("oms.pdd.fulfillment_order_conversion", "履约订单转化", "oms.pdd", 3, "oms", False, True, True, None, None, 40, True),

    ("oms.taobao", "淘宝", "oms", 2, "oms", False, True, True, None, None, 20, True),
    ("oms.taobao.import", "订单导入", "oms.taobao", 3, "oms", False, True, True, None, None, 10, True),
    ("oms.taobao.platform_order_mirror", "平台订单镜像", "oms.taobao", 3, "oms", False, True, True, None, None, 20, True),
    ("oms.taobao.fsku_mapping", "商品映射", "oms.taobao", 3, "oms", False, True, True, None, None, 30, True),
    ("oms.taobao.fulfillment_order_conversion", "履约订单转化", "oms.taobao", 3, "oms", False, True, True, None, None, 40, True),

    ("oms.jd", "京东", "oms", 2, "oms", False, True, True, None, None, 30, True),
    ("oms.jd.import", "订单导入", "oms.jd", 3, "oms", False, True, True, None, None, 10, True),
    ("oms.jd.platform_order_mirror", "平台订单镜像", "oms.jd", 3, "oms", False, True, True, None, None, 20, True),
    ("oms.jd.fsku_mapping", "商品映射", "oms.jd", 3, "oms", False, True, True, None, None, 30, True),
    ("oms.jd.fulfillment_order_conversion", "履约订单转化", "oms.jd", 3, "oms", False, True, True, None, None, 40, True),
)

OMS_ROUTE_ROWS = (
    ("/oms", "oms", 10),
    ("/oms/pdd", "oms.pdd.import", 20),
    ("/oms/pdd/import", "oms.pdd.import", 21),
    ("/oms/pdd/platform-order-mirror", "oms.pdd.platform_order_mirror", 22),
    ("/oms/pdd/fsku-mapping", "oms.pdd.fsku_mapping", 23),
    ("/oms/pdd/fulfillment-order-conversion", "oms.pdd.fulfillment_order_conversion", 24),

    ("/oms/taobao", "oms.taobao.import", 30),
    ("/oms/taobao/import", "oms.taobao.import", 31),
    ("/oms/taobao/platform-order-mirror", "oms.taobao.platform_order_mirror", 32),
    ("/oms/taobao/fsku-mapping", "oms.taobao.fsku_mapping", 33),
    ("/oms/taobao/fulfillment-order-conversion", "oms.taobao.fulfillment_order_conversion", 34),

    ("/oms/jd", "oms.jd.import", 40),
    ("/oms/jd/import", "oms.jd.import", 41),
    ("/oms/jd/platform-order-mirror", "oms.jd.platform_order_mirror", 42),
    ("/oms/jd/fsku-mapping", "oms.jd.fsku_mapping", 43),
    ("/oms/jd/fulfillment-order-conversion", "oms.jd.fulfillment_order_conversion", 44),
)


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 旧平台采集权限先映射给 OMS 权限，避免用户入口突然丢失。
    op.execute(
        """
        INSERT INTO permissions (name)
        VALUES ('page.oms.read'), ('page.oms.write')
        ON CONFLICT (name) DO NOTHING
        """
    )

    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.platform_order_ingestion.read' AS old_name, 'page.oms.read' AS new_name
          UNION ALL
          SELECT 'page.platform_order_ingestion.write', 'page.oms.write'
        ),
        pairs AS (
          SELECT DISTINCT up.user_id, newp.id AS permission_id
          FROM mappings m
          JOIN permissions oldp ON oldp.name = m.old_name
          JOIN user_permissions up ON up.permission_id = oldp.id
          JOIN permissions newp ON newp.name = m.new_name
        )
        INSERT INTO user_permissions (user_id, permission_id)
        SELECT user_id, permission_id
        FROM pairs
        ON CONFLICT (user_id, permission_id) DO NOTHING
        """
    )

    # 2) 删除旧 platform_order_ingestion 页面树与路由。
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE page_code = 'platform_order_ingestion'
           OR page_code LIKE 'platform_order_ingestion.%'
           OR route_prefix = '/platform-order-ingestion'
           OR route_prefix LIKE '/platform-order-ingestion/%'
        """
    )

    op.execute(
        f"""
        DELETE FROM page_registry
        WHERE code IN ({_sql_list(OLD_PLATFORM_PAGE_CODES[:6])})
        """
    )
    op.execute(
        f"""
        DELETE FROM page_registry
        WHERE code IN ({_sql_list(OLD_PLATFORM_PAGE_CODES[6:10])})
        """
    )
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'platform_order_ingestion'
        """
    )

    op.execute(
        f"""
        DELETE FROM permissions
        WHERE name IN ({_sql_list(OLD_PLATFORM_PERMISSION_NAMES)})
        """
    )

    # 3) 收紧 page_registry domain_code，移除 platform_order_ingestion 旧域。
    op.execute("ALTER TABLE page_registry DROP CONSTRAINT IF EXISTS ck_page_registry_domain_code")
    op.execute(
        """
        ALTER TABLE page_registry
        ADD CONSTRAINT ck_page_registry_domain_code
        CHECK (
          domain_code IN (
            'finance',
            'oms',
            'pms',
            'procurement',
            'wms',
            'shipping_assist',
            'admin',
            'inbound'
          )
        )
        """
    )

    # 4) 注册 OMS 三平台四页面。
    for (
        code,
        name,
        parent_code,
        level,
        domain_code,
        show_in_topbar,
        show_in_sidebar,
        inherit_permissions,
        read_permission,
        write_permission,
        sort_order,
        is_active,
    ) in OMS_PAGE_ROWS:
        op.execute(
            f"""
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
              '{code}',
              '{name}',
              {'NULL' if parent_code is None else "'" + parent_code + "'"},
              {level},
              '{domain_code}',
              {'TRUE' if show_in_topbar else 'FALSE'},
              {'TRUE' if show_in_sidebar else 'FALSE'},
              {'TRUE' if inherit_permissions else 'FALSE'},
              {'NULL' if read_permission is None else "(SELECT id FROM permissions WHERE name = '" + read_permission + "')"},
              {'NULL' if write_permission is None else "(SELECT id FROM permissions WHERE name = '" + write_permission + "')"},
              {sort_order},
              {'TRUE' if is_active else 'FALSE'}
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
        DELETE FROM page_route_prefixes
        WHERE route_prefix = '/oms'
           OR route_prefix LIKE '/oms/pdd%'
           OR route_prefix LIKE '/oms/taobao%'
           OR route_prefix LIKE '/oms/jd%'
        """
    )

    for route_prefix, page_code, sort_order in OMS_ROUTE_ROWS:
        op.execute(
            f"""
            INSERT INTO page_route_prefixes (
              page_code,
              route_prefix,
              sort_order,
              is_active
            )
            VALUES (
              '{page_code}',
              '{route_prefix}',
              {sort_order},
              TRUE
            )
            ON CONFLICT (route_prefix) DO UPDATE
            SET
              page_code = EXCLUDED.page_code,
              sort_order = EXCLUDED.sort_order,
              is_active = EXCLUDED.is_active
            """
        )

    # 5) 删除 WMS 主系统旧平台采集数据表。
    #    注意：这是破坏性退役；数据恢复依赖升级前的 pg_dump 备份。
    op.execute("DROP TABLE IF EXISTS pdd_order_order_mappings CASCADE")
    op.execute("DROP TABLE IF EXISTS platform_order_pull_job_run_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS platform_order_pull_job_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS platform_order_pull_jobs CASCADE")
    op.execute("DROP TABLE IF EXISTS pdd_order_items CASCADE")
    op.execute("DROP TABLE IF EXISTS taobao_order_items CASCADE")
    op.execute("DROP TABLE IF EXISTS jd_order_items CASCADE")
    op.execute("DROP TABLE IF EXISTS pdd_orders CASCADE")
    op.execute("DROP TABLE IF EXISTS taobao_orders CASCADE")
    op.execute("DROP TABLE IF EXISTS jd_orders CASCADE")
    op.execute("DROP TABLE IF EXISTS store_platform_credentials CASCADE")
    op.execute("DROP TABLE IF EXISTS store_platform_connections CASCADE")
    op.execute("DROP TABLE IF EXISTS pdd_app_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS taobao_app_configs CASCADE")
    op.execute("DROP TABLE IF EXISTS jd_app_configs CASCADE")


def downgrade() -> None:
    """Downgrade schema."""

    raise RuntimeError(
        "This migration retires WMS platform ingestion tables and cannot restore dropped data. "
        "Restore from the pg_dump backup created before upgrade if rollback is required."
    )
