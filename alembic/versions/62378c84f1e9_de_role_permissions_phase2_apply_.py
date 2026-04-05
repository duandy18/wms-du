# alembic/versions/62378c84f1e9_de_role_permissions_phase2_apply_.py
"""de_role_permissions_phase2_apply_subpages_seed_fix2

Revision ID: 62378c84f1e9
Revises: 0cee7380732a
Create Date: 2026-04-05 16:25:15.597643

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "62378c84f1e9"
down_revision: Union[str, Sequence[str], None] = "0cee7380732a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) seed 二级页面
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
        SELECT *
        FROM (
            -- inbound
            SELECT 'wms.inbound.receiving'::varchar(64), '原子入库'::varchar(64), 'wms.inbound'::varchar(64), 2, 'wms'::varchar(32), FALSE, TRUE, TRUE, NULL::integer, NULL::integer, 10, TRUE

            UNION ALL

            -- order outbound
            SELECT 'wms.order_outbound.pick_tasks', '拣货任务', 'wms.order_outbound', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE
            UNION ALL
            SELECT 'wms.order_outbound.dashboard', '出库看板', 'wms.order_outbound', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE

            UNION ALL

            -- order management -> oms
            SELECT 'wms.order_management.pdd_stores', '拼多多店铺', 'wms.order_management', 2, 'oms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE
            UNION ALL
            SELECT 'wms.order_management.pdd_orders', '拼多多订单', 'wms.order_management', 2, 'oms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE
            UNION ALL
            SELECT 'wms.order_management.taobao_stores', '淘宝店铺', 'wms.order_management', 2, 'oms', FALSE, TRUE, TRUE, NULL, NULL, 30, TRUE
            UNION ALL
            SELECT 'wms.order_management.taobao_orders', '淘宝订单', 'wms.order_management', 2, 'oms', FALSE, TRUE, TRUE, NULL, NULL, 40, TRUE
            UNION ALL
            SELECT 'wms.order_management.jd_stores', '京东店铺', 'wms.order_management', 2, 'oms', FALSE, TRUE, TRUE, NULL, NULL, 50, TRUE
            UNION ALL
            SELECT 'wms.order_management.jd_orders', '京东订单', 'wms.order_management', 2, 'oms', FALSE, TRUE, TRUE, NULL, NULL, 60, TRUE

            UNION ALL

            -- logistics -> tms
            SELECT 'wms.logistics.shipment_prepare', '发运准备', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE
            UNION ALL
            SELECT 'wms.logistics.dispatch', '发货作业', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE
            UNION ALL
            SELECT 'wms.logistics.providers', '承运商配置', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 30, TRUE
            UNION ALL
            SELECT 'wms.logistics.waybill_configs', '电子面单配置', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 40, TRUE
            UNION ALL
            SELECT 'wms.logistics.pricing', '运价管理', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 50, TRUE
            UNION ALL
            SELECT 'wms.logistics.templates', '运价模板', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 60, TRUE
            UNION ALL
            SELECT 'wms.logistics.records', '物流记录', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 70, TRUE
            UNION ALL
            SELECT 'wms.logistics.billing_items', '对账项管理', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 80, TRUE
            UNION ALL
            SELECT 'wms.logistics.reconciliation', '物流对账', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 90, TRUE
            UNION ALL
            SELECT 'wms.logistics.reports', '物流报表', 'wms.logistics', 2, 'tms', FALSE, TRUE, TRUE, NULL, NULL, 100, TRUE

            UNION ALL

            -- internal ops
            SELECT 'wms.internal_ops.count', '盘点作业', 'wms.internal_ops', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE
            UNION ALL
            SELECT 'wms.internal_ops.internal_outbound', '内部出库', 'wms.internal_ops', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE

            UNION ALL

            -- inventory
            SELECT 'wms.inventory.snapshot', '库存快照', 'wms.inventory', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE
            UNION ALL
            SELECT 'wms.inventory.ledger', '库存台账', 'wms.inventory', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE

            UNION ALL

            -- analytics
            SELECT 'wms.analytics.finance', '财务分析', 'wms.analytics', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE

            UNION ALL

            -- masterdata transitional area
            SELECT 'wms.masterdata.items', '商品管理', 'wms.masterdata', 2, 'pms', FALSE, TRUE, TRUE, NULL, NULL, 10, TRUE
            UNION ALL
            SELECT 'wms.masterdata.warehouses', '仓库管理', 'wms.masterdata', 2, 'wms', FALSE, TRUE, TRUE, NULL, NULL, 20, TRUE
            UNION ALL
            SELECT 'wms.masterdata.suppliers', '供应商管理', 'wms.masterdata', 2, 'procurement', FALSE, TRUE, TRUE, NULL, NULL, 30, TRUE
        ) t
        ON CONFLICT (code) DO NOTHING
        """
    )

    # 2) route_prefix -> 二级页面
    op.execute(
        """
        WITH mapping(route_prefix, page_code) AS (
            VALUES
              ('/purchase-orders', 'wms.inbound.receiving'),
              ('/inbound', 'wms.inbound.receiving'),

              ('/outbound/pick-tasks', 'wms.order_outbound.pick_tasks'),
              ('/outbound/dashboard', 'wms.order_outbound.dashboard'),

              ('/oms/pdd/stores', 'wms.order_management.pdd_stores'),
              ('/oms/pdd/orders', 'wms.order_management.pdd_orders'),
              ('/oms/taobao/stores', 'wms.order_management.taobao_stores'),
              ('/oms/taobao/orders', 'wms.order_management.taobao_orders'),
              ('/oms/jd/stores', 'wms.order_management.jd_stores'),
              ('/oms/jd/orders', 'wms.order_management.jd_orders'),

              ('/tms/shipment-prepare', 'wms.logistics.shipment_prepare'),
              ('/tms/dispatch', 'wms.logistics.dispatch'),
              ('/tms/providers', 'wms.logistics.providers'),
              ('/tms/waybill-configs', 'wms.logistics.waybill_configs'),
              ('/tms/pricing', 'wms.logistics.pricing'),
              ('/tms/templates', 'wms.logistics.templates'),
              ('/tms/records', 'wms.logistics.records'),
              ('/tms/billing/items', 'wms.logistics.billing_items'),
              ('/tms/reconciliation', 'wms.logistics.reconciliation'),
              ('/tms/reports', 'wms.logistics.reports'),

              ('/count', 'wms.internal_ops.count'),
              ('/outbound/internal-outbound', 'wms.internal_ops.internal_outbound'),

              ('/snapshot', 'wms.inventory.snapshot'),
              ('/inventory/ledger', 'wms.inventory.ledger'),

              ('/finance', 'wms.analytics.finance'),

              ('/items', 'wms.masterdata.items'),
              ('/warehouses', 'wms.masterdata.warehouses'),
              ('/suppliers', 'wms.masterdata.suppliers')
        )
        UPDATE page_route_prefixes prp
           SET page_code = m.page_code
          FROM mapping m
         WHERE prp.route_prefix = m.route_prefix
        """
    )


def downgrade() -> None:
    # 1) route_prefix 挂回一级页面
    op.execute(
        """
        WITH mapping(route_prefix, page_code) AS (
            VALUES
              ('/purchase-orders', 'wms.inbound'),
              ('/inbound', 'wms.inbound'),

              ('/outbound/pick-tasks', 'wms.order_outbound'),
              ('/outbound/dashboard', 'wms.order_outbound'),

              ('/oms/pdd/stores', 'wms.order_management'),
              ('/oms/pdd/orders', 'wms.order_management'),
              ('/oms/taobao/stores', 'wms.order_management'),
              ('/oms/taobao/orders', 'wms.order_management'),
              ('/oms/jd/stores', 'wms.order_management'),
              ('/oms/jd/orders', 'wms.order_management'),

              ('/tms/shipment-prepare', 'wms.logistics'),
              ('/tms/dispatch', 'wms.logistics'),
              ('/tms/providers', 'wms.logistics'),
              ('/tms/waybill-configs', 'wms.logistics'),
              ('/tms/pricing', 'wms.logistics'),
              ('/tms/templates', 'wms.logistics'),
              ('/tms/records', 'wms.logistics'),
              ('/tms/billing/items', 'wms.logistics'),
              ('/tms/reconciliation', 'wms.logistics'),
              ('/tms/reports', 'wms.logistics'),

              ('/count', 'wms.internal_ops'),
              ('/outbound/internal-outbound', 'wms.internal_ops'),

              ('/snapshot', 'wms.inventory'),
              ('/inventory/ledger', 'wms.inventory'),

              ('/finance', 'wms.analytics'),

              ('/items', 'wms.masterdata'),
              ('/warehouses', 'wms.masterdata'),
              ('/suppliers', 'wms.masterdata')
        )
        UPDATE page_route_prefixes prp
           SET page_code = m.page_code
          FROM mapping m
         WHERE prp.route_prefix = m.route_prefix
        """
    )

    # 2) 删除 fix2 seed 的二级页面
    op.execute(
        """
        DELETE FROM page_registry
         WHERE code IN (
            'wms.inbound.receiving',

            'wms.order_outbound.pick_tasks',
            'wms.order_outbound.dashboard',

            'wms.order_management.pdd_stores',
            'wms.order_management.pdd_orders',
            'wms.order_management.taobao_stores',
            'wms.order_management.taobao_orders',
            'wms.order_management.jd_stores',
            'wms.order_management.jd_orders',

            'wms.logistics.shipment_prepare',
            'wms.logistics.dispatch',
            'wms.logistics.providers',
            'wms.logistics.waybill_configs',
            'wms.logistics.pricing',
            'wms.logistics.templates',
            'wms.logistics.records',
            'wms.logistics.billing_items',
            'wms.logistics.reconciliation',
            'wms.logistics.reports',

            'wms.internal_ops.count',
            'wms.internal_ops.internal_outbound',

            'wms.inventory.snapshot',
            'wms.inventory.ledger',

            'wms.analytics.finance',

            'wms.masterdata.items',
            'wms.masterdata.warehouses',
            'wms.masterdata.suppliers'
         )
        """
    )
