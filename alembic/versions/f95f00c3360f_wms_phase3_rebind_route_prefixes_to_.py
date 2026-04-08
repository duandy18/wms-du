"""wms_phase3_rebind_route_prefixes_to_three_level_pages

Revision ID: f95f00c3360f
Revises: 01ba4e53a8a6
Create Date: 2026-04-07 17:17:10.514231

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f95f00c3360f"
down_revision: Union[str, Sequence[str], None] = "01ba4e53a8a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1) 新增 / 更新 route_prefix -> 新二级 / 三级页映射
    #
    # 说明：
    # - 已有旧前缀：通过 ON CONFLICT(route_prefix) DO UPDATE 重挂 page_code
    # - 新增动态前缀：直接补录，供前端最长前缀 / 动态段匹配使用
    # - 注意：SQLAlchemy text() 会把 :param 识别为绑定参数，
    #   因此动态 route_prefix 里的冒号必须写成 \:param
    op.execute(
        """
        INSERT INTO page_route_prefixes (
          page_code,
          route_prefix,
          sort_order,
          is_active
        )
        VALUES
          -- inventory
          ('wms.inventory.snapshot', '/snapshot', 10, TRUE),
          ('wms.inventory.ledger', '/inventory/ledger', 20, TRUE),

          -- inbound.atomic
          ('wms.inbound.atomic', '/inbound', 10, TRUE),

          -- inbound.purchase
          ('wms.inbound.purchase', '/purchase-orders', 20, TRUE),
          ('wms.inbound.purchase', '/purchase-orders/overview', 21, TRUE),
          ('wms.inbound.purchase', '/purchase-orders/new-v2', 22, TRUE),
          ('wms.inbound.purchase', '/purchase-orders/\\:poId', 23, TRUE),
          ('wms.inbound.purchase', '/receive-tasks/\\:taskId', 24, TRUE),

          -- inbound.returns
          ('wms.inbound.returns', '/return-tasks/\\:taskId', 30, TRUE),

          -- outbound
          ('wms.outbound.atomic', '/outbound/internal-outbound', 10, TRUE),
          ('wms.outbound.order', '/outbound/pick-tasks', 20, TRUE),
          ('wms.outbound.order', '/outbound/dashboard', 21, TRUE),

          -- count
          ('wms.count.tasks', '/count', 10, TRUE),

          -- warehouses
          ('wms.warehouses', '/warehouses', 10, TRUE),
          ('wms.warehouses', '/warehouses/new', 11, TRUE),
          ('wms.warehouses', '/warehouses/\\:warehouseId', 12, TRUE)
        ON CONFLICT (route_prefix) DO UPDATE
        SET
          page_code = EXCLUDED.page_code,
          sort_order = EXCLUDED.sort_order,
          is_active = EXCLUDED.is_active
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 1) 先把历史已有前缀挂回旧两层 / 旧细二级壳
    op.execute(
        """
        WITH mapping(route_prefix, page_code) AS (
            VALUES
              ('/snapshot', 'wms.inventory.snapshot'),
              ('/inventory/ledger', 'wms.inventory.ledger'),

              ('/inbound', 'wms.inbound.receiving'),
              ('/purchase-orders', 'wms.inbound.receiving'),

              ('/return-tasks/\\:taskId', 'wms.inbound.receiving'),

              ('/outbound/internal-outbound', 'wms.internal_ops.internal_outbound'),
              ('/outbound/pick-tasks', 'wms.order_outbound.pick_tasks'),
              ('/outbound/dashboard', 'wms.order_outbound.dashboard'),

              ('/count', 'wms.internal_ops.count'),

              ('/warehouses', 'wms.masterdata.warehouses')
        )
        UPDATE page_route_prefixes prp
           SET page_code = m.page_code
          FROM mapping m
         WHERE prp.route_prefix = m.route_prefix
        """
    )

    # 2) 删除本次新增的更细动态 / 具体前缀
    op.execute(
        """
        DELETE FROM page_route_prefixes
        WHERE route_prefix IN (
          '/purchase-orders/overview',
          '/purchase-orders/new-v2',
          '/purchase-orders/\\:poId',
          '/receive-tasks/\\:taskId',
          '/warehouses/new',
          '/warehouses/\\:warehouseId'
        )
        """
    )
