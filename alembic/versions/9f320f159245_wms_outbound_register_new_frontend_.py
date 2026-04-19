"""wms_outbound_register_new_frontend_pages_and_rebind_route_prefixes

Revision ID: 9f320f159245
Revises: 41f8dda5c2ae
Create Date: 2026-04-19 22:05:16.737835

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9f320f159245"
down_revision: Union[str, Sequence[str], None] = "41f8dda5c2ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 注册 / 收正 wms.outbound 下的新四个三级页面
    #    - summary:    出库汇总
    #    - order:      订单出库（保留并收正）
    #    - manual_docs:手动出库单据
    #    - manual:     手动出库
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
            'wms.outbound.summary',
            '出库汇总',
            'wms.outbound',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            10,
            TRUE
          ),
          (
            'wms.outbound.order',
            '订单出库',
            'wms.outbound',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            TRUE
          ),
          (
            'wms.outbound.manual_docs',
            '手动出库单据',
            'wms.outbound',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            30,
            TRUE
          ),
          (
            'wms.outbound.manual',
            '手动出库',
            'wms.outbound',
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

    # 2) 注册新主路径 + 旧路径兼容前缀
    #    说明：
    #    - 新主路径：
    #        /outbound/summary
    #        /outbound/order
    #        /outbound/manual-docs
    #        /outbound/manual
    #    - 旧兼容路径：
    #        /outbound/dashboard            -> wms.outbound.summary
    #        /inventory/outbound-dashboard -> wms.outbound.summary
    #        /outbound/pick-tasks          -> wms.outbound.order
    #        /outbound/internal-outbound   -> wms.outbound.manual_docs
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('wms.outbound.summary',     '/outbound/summary',            10,  TRUE),
          ('wms.outbound.order',       '/outbound/order',              20,  TRUE),
          ('wms.outbound.manual_docs', '/outbound/manual-docs',        30,  TRUE),
          ('wms.outbound.manual',      '/outbound/manual',             40,  TRUE),

          ('wms.outbound.summary',     '/outbound/dashboard',          110, TRUE),
          ('wms.outbound.summary',     '/inventory/outbound-dashboard',111, TRUE),
          ('wms.outbound.order',       '/outbound/pick-tasks',         120, TRUE),
          ('wms.outbound.manual_docs', '/outbound/internal-outbound',  130, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 3) 退役旧 atomic 页码
    #    route_prefixes.page_code -> page_registry.code 是 ON DELETE CASCADE；
    #    但此处 /outbound/internal-outbound 已先重绑到 wms.outbound.manual_docs，
    #    所以删除 wms.outbound.atomic 不会丢掉兼容路径。
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'wms.outbound.atomic'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复旧 atomic 页码
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
            'wms.outbound.atomic',
            '原子出库',
            'wms.outbound',
            3,
            'wms',
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

    # 2) 先删除本次新增的新主路径
    #    兼容路径中的旧 route_prefix 会在下一步被重绑回旧页面码，因此这里不删旧路径本身。
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/outbound/summary',
          '/outbound/order',
          '/outbound/manual-docs',
          '/outbound/manual',
          '/inventory/outbound-dashboard'
        )
        """
    )

    # 3) 将旧兼容路径重绑回旧页面真相
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('wms.outbound.atomic', '/outbound/internal-outbound', 10, TRUE),
          ('wms.outbound.order',  '/outbound/pick-tasks',        20, TRUE),
          ('wms.outbound.order',  '/outbound/dashboard',         21, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 4) 删除本次新增的 3 个新页面；
    #    wms.outbound.order 是旧页面码，保留。
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.outbound.summary',
          'wms.outbound.manual_docs',
          'wms.outbound.manual'
        )
        """
    )
