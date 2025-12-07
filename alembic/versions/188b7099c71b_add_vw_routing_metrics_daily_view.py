"""add vw_routing_metrics_daily view

Revision ID: 188b7099c71b
Revises: 28603776bfc6
Create Date: 2025-11-19 09:55:06.500412

注意：
- 这里 JOIN 条件是 ON s.platform = o.platform AND s.shop_id = o.shop_id
- 绝对不能再出现 o.store_id 这样的字段名
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "188b7099c71b"
down_revision: Union[str, Sequence[str], None] = "28603776bfc6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create or replace routing metrics view.

    视图目标：
    - day: date_trunc('day', orders.created_at)
    - platform, shop_id: 从 orders / stores 对齐
    - route_mode: 从 stores.route_mode 读取（orders 当前没这个字段）
    - warehouse_id: 来自 orders.warehouse_id

    指标：
    - routed_orders: warehouse_id 非空的订单数
    - failed_orders: warehouse_id 为空的订单数
    """
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_routing_metrics_daily AS
        SELECT
            date_trunc('day', o.created_at) AS day,
            o.platform,
            o.shop_id,
            COALESCE(s.route_mode, 'FALLBACK') AS route_mode,
            o.warehouse_id,
            COUNT(*) FILTER (WHERE o.warehouse_id IS NOT NULL) AS routed_orders,
            COUNT(*) FILTER (WHERE o.warehouse_id IS NULL)     AS failed_orders
        FROM orders o
        LEFT JOIN stores s
          ON s.platform = o.platform
         AND s.shop_id  = o.shop_id
        GROUP BY
            date_trunc('day', o.created_at),
            o.platform,
            o.shop_id,
            COALESCE(s.route_mode, 'FALLBACK'),
            o.warehouse_id;
        """
    )


def downgrade() -> None:
    """Drop view."""
    op.execute("DROP VIEW IF EXISTS vw_routing_metrics_daily;")
