"""reparent phase1 domain subpages and backfill user_permissions

Revision ID: dcd0f7b59422
Revises: bfd9ddf52eb9
Create Date: 2026-04-07 11:45:02.649848

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "dcd0f7b59422"
down_revision: Union[str, Sequence[str], None] = "bfd9ddf52eb9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) analytics：财务分析从 wms.analytics 改挂到 analytics，
    #    并把真实领域码从 wms 改成 analytics。
    op.execute(
        """
        UPDATE page_registry
        SET
          parent_code = 'analytics',
          domain_code = 'analytics'
        WHERE code = 'wms.analytics.finance'
        """
    )

    # 2) oms：订单管理子页改挂到 oms 一级页。
    op.execute(
        """
        UPDATE page_registry
        SET parent_code = 'oms'
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

    # 3) tms：物流子页改挂到 tms 一级页。
    op.execute(
        """
        UPDATE page_registry
        SET parent_code = 'tms'
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

    # 4) pms：商品 / 供应商改挂到 pms 一级页。
    #    warehouses 仍留在 wms.masterdata，不在本次改挂范围内。
    op.execute(
        """
        UPDATE page_registry
        SET parent_code = 'pms'
        WHERE code IN (
          'wms.masterdata.items',
          'wms.masterdata.suppliers'
        )
        """
    )

    # 5) 把旧一级页权限映射补发到新的一级页权限。
    #    这里只补发，不删除旧权限。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.wms.analytics.read' AS source_name, 'page.analytics.read' AS target_name
          UNION ALL
          SELECT 'page.wms.analytics.write', 'page.analytics.write'
          UNION ALL
          SELECT 'page.wms.order_management.read', 'page.oms.read'
          UNION ALL
          SELECT 'page.wms.order_management.write', 'page.oms.write'
          UNION ALL
          SELECT 'page.wms.logistics.read', 'page.tms.read'
          UNION ALL
          SELECT 'page.wms.logistics.write', 'page.tms.write'
          UNION ALL
          SELECT 'page.wms.masterdata.read', 'page.pms.read'
          UNION ALL
          SELECT 'page.wms.masterdata.write', 'page.pms.write'
        ),
        pairs AS (
          SELECT DISTINCT
            up.user_id,
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
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 撤回本次补发的新一级页权限。
    #    只删除“当前仍拥有旧一级页权限”的用户上的对应新权限，避免过度删除。
    op.execute(
        """
        WITH mappings AS (
          SELECT 'page.wms.analytics.read' AS source_name, 'page.analytics.read' AS target_name
          UNION ALL
          SELECT 'page.wms.analytics.write', 'page.analytics.write'
          UNION ALL
          SELECT 'page.wms.order_management.read', 'page.oms.read'
          UNION ALL
          SELECT 'page.wms.order_management.write', 'page.oms.write'
          UNION ALL
          SELECT 'page.wms.logistics.read', 'page.tms.read'
          UNION ALL
          SELECT 'page.wms.logistics.write', 'page.tms.write'
          UNION ALL
          SELECT 'page.wms.masterdata.read', 'page.pms.read'
          UNION ALL
          SELECT 'page.wms.masterdata.write', 'page.pms.write'
        )
        DELETE FROM user_permissions up
        USING mappings m, permissions tp, permissions sp, user_permissions old_up
        WHERE up.permission_id = tp.id
          AND tp.name = m.target_name
          AND sp.name = m.source_name
          AND old_up.permission_id = sp.id
          AND old_up.user_id = up.user_id
        """
    )

    # 2) pms：商品 / 供应商改挂回 wms.masterdata。
    op.execute(
        """
        UPDATE page_registry
        SET parent_code = 'wms.masterdata'
        WHERE code IN (
          'wms.masterdata.items',
          'wms.masterdata.suppliers'
        )
        """
    )

    # 3) tms：物流子页改挂回 wms.logistics。
    op.execute(
        """
        UPDATE page_registry
        SET parent_code = 'wms.logistics'
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

    # 4) oms：订单管理子页改挂回 wms.order_management。
    op.execute(
        """
        UPDATE page_registry
        SET parent_code = 'wms.order_management'
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

    # 5) analytics：财务分析改挂回 wms.analytics，并把领域码改回 wms。
    op.execute(
        """
        UPDATE page_registry
        SET
          parent_code = 'wms.analytics',
          domain_code = 'wms'
        WHERE code = 'wms.analytics.finance'
        """
    )
