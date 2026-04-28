"""oms merge import pages into platform mirrors

Revision ID: 3eb4afa444e5
Revises: 2d73c129cb75
Create Date: 2026-04-28

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "3eb4afa444e5"
down_revision: Union[str, Sequence[str], None] = "2d73c129cb75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PLATFORM_ROWS = (
    ("pdd", "oms.pdd", "oms.pdd.import", "oms.pdd.platform_order_mirror", "oms.pdd.fsku_mapping", "oms.pdd.fulfillment_order_conversion", 20),
    ("taobao", "oms.taobao", "oms.taobao.import", "oms.taobao.platform_order_mirror", "oms.taobao.fsku_mapping", "oms.taobao.fulfillment_order_conversion", 30),
    ("jd", "oms.jd", "oms.jd.import", "oms.jd.platform_order_mirror", "oms.jd.fsku_mapping", "oms.jd.fulfillment_order_conversion", 40),
)


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def upgrade() -> None:
    """Merge each platform import page into its platform-order-mirror page."""

    import_page_codes = tuple(row[2] for row in PLATFORM_ROWS)
    import_route_prefixes = tuple(f"/oms/{row[0]}/import" for row in PLATFORM_ROWS)

    # 1) 删除独立 import 路由。
    op.execute(
        f"""
        DELETE FROM page_route_prefixes
        WHERE page_code IN ({_sql_list(import_page_codes)})
           OR route_prefix IN ({_sql_list(import_route_prefixes)})
        """
    )

    # 2) 平台根路由统一指向平台订单镜像页。
    for platform, _root_code, _import_code, mirror_code, fsku_code, conversion_code, base_sort in PLATFORM_ROWS:
        op.execute(
            f"""
            INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
            VALUES ('/oms/{platform}', '{mirror_code}', {base_sort}, TRUE)
            ON CONFLICT (route_prefix) DO UPDATE
            SET
              page_code = EXCLUDED.page_code,
              sort_order = EXCLUDED.sort_order,
              is_active = TRUE
            """
        )

        op.execute(
            f"""
            UPDATE page_route_prefixes
               SET sort_order = CASE route_prefix
                   WHEN '/oms/{platform}/platform-order-mirror' THEN {base_sort + 1}
                   WHEN '/oms/{platform}/fsku-mapping' THEN {base_sort + 2}
                   WHEN '/oms/{platform}/fulfillment-order-conversion' THEN {base_sort + 3}
                   ELSE sort_order
                 END,
                 is_active = TRUE
             WHERE route_prefix IN (
               '/oms/{platform}/platform-order-mirror',
               '/oms/{platform}/fsku-mapping',
               '/oms/{platform}/fulfillment-order-conversion'
             )
            """
        )

        op.execute(
            f"""
            UPDATE page_registry
               SET sort_order = CASE code
                   WHEN '{mirror_code}' THEN 10
                   WHEN '{fsku_code}' THEN 20
                   WHEN '{conversion_code}' THEN 30
                   ELSE sort_order
                 END,
                 show_in_sidebar = TRUE,
                 is_active = TRUE
             WHERE code IN ('{mirror_code}', '{fsku_code}', '{conversion_code}')
            """
        )

    # 3) 删除独立 import 页面节点；不保留导航兼容页。
    op.execute(
        f"""
        DELETE FROM page_registry
        WHERE code IN ({_sql_list(import_page_codes)})
        """
    )


def downgrade() -> None:
    """Restore separated import pages and routes."""

    for platform, root_code, import_code, mirror_code, fsku_code, conversion_code, base_sort in PLATFORM_ROWS:
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
              '{import_code}',
              '订单导入',
              '{root_code}',
              3,
              'oms',
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
              sort_order = EXCLUDED.sort_order,
              is_active = EXCLUDED.is_active
            """
        )

        op.execute(
            f"""
            UPDATE page_registry
               SET sort_order = CASE code
                   WHEN '{import_code}' THEN 10
                   WHEN '{mirror_code}' THEN 20
                   WHEN '{fsku_code}' THEN 30
                   WHEN '{conversion_code}' THEN 40
                   ELSE sort_order
                 END,
                 show_in_sidebar = TRUE,
                 is_active = TRUE
             WHERE code IN ('{import_code}', '{mirror_code}', '{fsku_code}', '{conversion_code}')
            """
        )

        op.execute(
            f"""
            INSERT INTO page_route_prefixes (route_prefix, page_code, sort_order, is_active)
            VALUES
              ('/oms/{platform}', '{import_code}', {base_sort}, TRUE),
              ('/oms/{platform}/import', '{import_code}', {base_sort + 1}, TRUE),
              ('/oms/{platform}/platform-order-mirror', '{mirror_code}', {base_sort + 2}, TRUE),
              ('/oms/{platform}/fsku-mapping', '{fsku_code}', {base_sort + 3}, TRUE),
              ('/oms/{platform}/fulfillment-order-conversion', '{conversion_code}', {base_sort + 4}, TRUE)
            ON CONFLICT (route_prefix) DO UPDATE
            SET
              page_code = EXCLUDED.page_code,
              sort_order = EXCLUDED.sort_order,
              is_active = TRUE
            """
        )
