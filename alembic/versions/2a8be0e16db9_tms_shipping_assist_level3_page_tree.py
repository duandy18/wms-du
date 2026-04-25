"""tms shipping assist level3 page tree

Revision ID: 2a8be0e16db9
Revises: 1f23051286cd
Create Date: 2026-04-25 17:53:32.353550

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2a8be0e16db9"
down_revision: Union[str, Sequence[str], None] = "1f23051286cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 一级模块：技术 code 仍保留 tms，产品名称改为“发货辅助”。
    # 本刀只治理导航 truth，不同步改 app/tms 目录、不改接口 URL、不引入新权限名。
    op.execute(
        """
        UPDATE page_registry
           SET name = '发货辅助',
               parent_code = NULL,
               level = 1,
               domain_code = 'tms',
               show_in_topbar = TRUE,
               show_in_sidebar = FALSE,
               inherit_permissions = FALSE,
               read_permission_id = (SELECT id FROM permissions WHERE name = 'page.tms.read'),
               write_permission_id = (SELECT id FROM permissions WHERE name = 'page.tms.write'),
               sort_order = 40,
               is_active = TRUE
         WHERE code = 'tms'
        """
    )

    # 2) 建立“发货辅助系统”三级页面树。
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
          ('tms.shipping', '发货', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE),
          ('tms.shipping.quote', '发货算价', 'tms.shipping', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE),
          ('tms.shipping.records', '发货记录', 'tms.shipping', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE),

          ('tms.pricing', '运价', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE),
          ('tms.pricing.providers', '快递网点', 'tms.pricing', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE),
          ('tms.pricing.bindings', '运价管理', 'tms.pricing', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE),
          ('tms.pricing.templates', '运价表', 'tms.pricing', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 30, TRUE),

          ('tms.billing', '对账', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 30, TRUE),
          ('tms.billing.items', '快递账单', 'tms.billing', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE),
          ('tms.billing.reconciliation', '物流对账', 'tms.billing', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE),

          ('tms.settings', '设置', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 40, TRUE),
          ('tms.settings.waybill', '电子面单配置', 'tms.settings', 3, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE)
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

    # 3) 现有 URL 不改，只把 route_prefix 重新绑定到新三级 page_code。
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES
          ('/tms/shipment-prepare', 'tms.shipping.quote', 10, TRUE),
          ('/tms/dispatch', 'tms.shipping.quote', 20, TRUE),
          ('/tms/records', 'tms.shipping.records', 30, TRUE),

          ('/tms/providers', 'tms.pricing.providers', 40, TRUE),
          ('/tms/pricing', 'tms.pricing.bindings', 50, TRUE),
          ('/tms/templates', 'tms.pricing.templates', 60, TRUE),

          ('/tms/billing/items', 'tms.billing.items', 70, TRUE),
          ('/tms/reconciliation', 'tms.billing.reconciliation', 80, TRUE),

          ('/tms/waybill-configs', 'tms.settings.waybill', 90, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 4) /tms/reports 暂不作为“发货辅助”主链路页面暴露。
    # 后续如果要保留，应单独设计为“成本报表”，再挂到对账/分析分支。
    op.execute(
        """
        DELETE FROM page_route_prefixes
         WHERE route_prefix = '/tms/reports'
        """
    )

    # 5) 删除旧 wms.logistics.* 页面壳。
    # route_prefix 已经先改绑，因此这里不会删除现役 /tms 页面映射。
    op.execute(
        """
        DELETE FROM page_registry
         WHERE code IN (
           'wms.logistics.shipment_prepare',
           'wms.logistics.dispatch',
           'wms.logistics.providers',
           'wms.logistics.waybill_configs',
           'wms.logistics.pricing',
           'wms.logistics.templates',
           'wms.logistics.records',
           'wms.logistics.billing_items',
           'wms.logistics.reconciliation',
           'wms.logistics.reports'
         )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 恢复旧一级模块名称。
    op.execute(
        """
        UPDATE page_registry
           SET name = '物流',
               parent_code = NULL,
               level = 1,
               domain_code = 'tms',
               show_in_topbar = TRUE,
               show_in_sidebar = FALSE,
               inherit_permissions = FALSE,
               read_permission_id = (SELECT id FROM permissions WHERE name = 'page.tms.read'),
               write_permission_id = (SELECT id FROM permissions WHERE name = 'page.tms.write'),
               sort_order = 40,
               is_active = TRUE
         WHERE code = 'tms'
        """
    )

    # 2) 恢复旧 wms.logistics.* 二级页面。
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
          ('wms.logistics.shipment_prepare', '发运准备', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE),
          ('wms.logistics.dispatch', '发货作业', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE),
          ('wms.logistics.providers', '承运商配置', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 30, TRUE),
          ('wms.logistics.waybill_configs', '电子面单配置', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 40, TRUE),
          ('wms.logistics.pricing', '运价管理', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 50, TRUE),
          ('wms.logistics.templates', '运价模板', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 60, TRUE),
          ('wms.logistics.records', '物流记录', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 70, TRUE),
          ('wms.logistics.billing_items', '对账项管理', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 80, TRUE),
          ('wms.logistics.reconciliation', '物流对账', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 90, TRUE),
          ('wms.logistics.reports', '物流报表', 'tms', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 100, TRUE)
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

    # 3) 恢复旧 route_prefix -> wms.logistics.* 映射。
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          route_prefix,
          page_code,
          sort_order,
          is_active
        )
        VALUES
          ('/tms/shipment-prepare', 'wms.logistics.shipment_prepare', 10, TRUE),
          ('/tms/dispatch', 'wms.logistics.dispatch', 20, TRUE),
          ('/tms/providers', 'wms.logistics.providers', 30, TRUE),
          ('/tms/waybill-configs', 'wms.logistics.waybill_configs', 40, TRUE),
          ('/tms/pricing', 'wms.logistics.pricing', 50, TRUE),
          ('/tms/templates', 'wms.logistics.templates', 60, TRUE),
          ('/tms/records', 'wms.logistics.records', 70, TRUE),
          ('/tms/billing/items', 'wms.logistics.billing_items', 80, TRUE),
          ('/tms/reconciliation', 'wms.logistics.reconciliation', 90, TRUE),
          ('/tms/reports', 'wms.logistics.reports', 100, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )

    # 4) 删除新三级树：先删三级，再删二级。
    op.execute(
        """
        DELETE FROM page_registry
         WHERE code IN (
           'tms.shipping.quote',
           'tms.shipping.records',
           'tms.pricing.providers',
           'tms.pricing.bindings',
           'tms.pricing.templates',
           'tms.billing.items',
           'tms.billing.reconciliation',
           'tms.settings.waybill'
         )
        """
    )

    op.execute(
        """
        DELETE FROM page_registry
         WHERE code IN (
           'tms.shipping',
           'tms.pricing',
           'tms.billing',
           'tms.settings'
         )
        """
    )
