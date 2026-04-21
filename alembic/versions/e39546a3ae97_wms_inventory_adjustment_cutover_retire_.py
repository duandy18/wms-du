"""wms_inventory_adjustment_cutover_retire_legacy_count_and_return_inbound_navigation

Revision ID: e39546a3ae97
Revises: f05df0c90c55
Create Date: 2026-04-21 16:54:23.027665

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e39546a3ae97"
down_revision: Union[str, Sequence[str], None] = "f05df0c90c55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 注册 WMS 二级页：库存调节
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
          'wms.inventory_adjustment',
          '库存调节',
          'wms',
          2,
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

    # 2) 注册 WMS 三级页：库存调节汇总 / 盘点作业 / 入库冲回 / 出库冲回 / 退单入库
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
            'wms.inventory_adjustment.summary',
            '库存调节汇总',
            'wms.inventory_adjustment',
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
            'wms.inventory_adjustment.count',
            '盘点作业',
            'wms.inventory_adjustment',
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
            'wms.inventory_adjustment.inbound_reversal',
            '入库冲回',
            'wms.inventory_adjustment',
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
            'wms.inventory_adjustment.outbound_reversal',
            '出库冲回',
            'wms.inventory_adjustment',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            40,
            TRUE
          ),
          (
            'wms.inventory_adjustment.return_inbound',
            '退单入库',
            'wms.inventory_adjustment',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            50,
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

    # 3) 注册新路由前缀
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('wms.inventory_adjustment.summary', '/inventory-adjustment', 10, TRUE),
          ('wms.inventory_adjustment.count', '/inventory-adjustment/count', 20, TRUE),
          ('wms.inventory_adjustment.inbound_reversal', '/inventory-adjustment/inbound-reversal', 30, TRUE),
          ('wms.inventory_adjustment.outbound_reversal', '/inventory-adjustment/outbound-reversal', 40, TRUE),
          ('wms.inventory_adjustment.return_inbound', '/inventory-adjustment/return-inbound', 50, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 4) 收正 WMS 入库树残留：
    #    历史环境里 wms.inbound.operations 可能被误置为 active。
    op.execute(
        """
        UPDATE page_route_prefixes
           SET page_code = 'wms.inbound.atomic'
         WHERE page_code = 'wms.inbound.operations'
        """
    )
    op.execute(
        """
        UPDATE page_registry
           SET is_active = FALSE
         WHERE code = 'wms.inbound.operations'
        """
    )

    # 5) 退役旧三级页
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.count.tasks',
          'wms.count.adjustments',
          'wms.inbound.returns',
          'inbound.returns'
        )
        """
    )

    # 6) 退役旧二级页：wms.count
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'wms.count'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复旧二级页：盘点
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
          'wms.count',
          '盘点',
          'wms',
          2,
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

    # 2) 恢复旧三级页：盘点作业 / 库存调整 / 退货入库单 / 退货收货
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
            'wms.count.tasks',
            '盘点作业',
            'wms.count',
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
            'wms.count.adjustments',
            '库存调整',
            'wms.count',
            3,
            'wms',
            FALSE,
            TRUE,
            TRUE,
            NULL,
            NULL,
            20,
            FALSE
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
            'wms.inbound.returns',
            '退货收货',
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

    # 3) 恢复旧路由前缀
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          ('wms.count.tasks', '/count', 10, TRUE),
          ('inbound.returns', '/inbound-receipts/returns', 30, TRUE),
          ('wms.inbound.returns', '/receiving/returns', 40, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 4) 恢复隐藏页状态（维持当前真实口径：operations 默认不展示）
    op.execute(
        """
        UPDATE page_registry
           SET is_active = FALSE
         WHERE code = 'wms.inbound.operations'
        """
    )

    # 5) 删除库存调节新三级页；对应新 route_prefix 自动级联删除
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code IN (
          'wms.inventory_adjustment.summary',
          'wms.inventory_adjustment.count',
          'wms.inventory_adjustment.inbound_reversal',
          'wms.inventory_adjustment.outbound_reversal',
          'wms.inventory_adjustment.return_inbound'
        )
        """
    )

    # 6) 删除库存调节新二级页
    op.execute(
        """
        DELETE FROM page_registry
        WHERE code = 'wms.inventory_adjustment'
        """
    )
