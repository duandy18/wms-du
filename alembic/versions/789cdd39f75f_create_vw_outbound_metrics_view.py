"""create vw_outbound_metrics view

Revision ID: 789cdd39f75f
Revises: fc9e07b38b04
Create Date: 2025-11-07 20:22:23.836895
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "789cdd39f75f"
down_revision: Union[str, Sequence[str], None] = "fc9e07b38b04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 口径：
    # - day：audit_events.created_at(UTC)::date 用于订单/发运；PICK 用 stock_ledger.occurred_at(UTC)::date
    # - platform：优先 meta->>'platform'，其次 split_part(ref,':',2)，最后 'UNKNOWN'
    # - warehouse_id：由 stock_ledger.location_id → locations.warehouse_id 推导；取不到记为 0
    view_sql = """
    CREATE OR REPLACE VIEW vw_outbound_metrics AS
    WITH ae AS (
      SELECT
        (meta->>'flow')  AS flow,
        (meta->>'event') AS event,
        COALESCE(meta->>'platform', NULLIF(split_part(ref, ':', 2), '')) AS platform,
        ref,
        (created_at AT TIME ZONE 'utc')::date AS day
      FROM audit_events
      WHERE category='OUTBOUND'
    ),
    orders AS (
      SELECT day, COALESCE(platform, 'UNKNOWN') AS platform, COUNT(DISTINCT ref) AS orders_created
      FROM ae
      WHERE flow='OUTBOUND' AND event='ORDER_CREATED'
      GROUP BY 1,2
    ),
    ships AS (
      SELECT day, COALESCE(platform, 'UNKNOWN') AS platform, COUNT(DISTINCT ref) AS ship_commits
      FROM ae
      WHERE flow='OUTBOUND' AND event='SHIP_COMMIT'
      GROUP BY 1,2
    ),
    picks AS (
      SELECT
        (l.occurred_at AT TIME ZONE 'utc')::date  AS day,               -- ★ 拣货日期：occurred_at
        COALESCE(ae.platform, 'UNKNOWN')          AS platform,          -- ★ 平台：优先审计 meta
        COALESCE(loc.warehouse_id, 0)             AS warehouse_id,      -- ★ 仓：location_id → locations.warehouse_id
        SUM(ABS(l.delta))                         AS pick_qty
      FROM stock_ledger l
      LEFT JOIN ae        ON ae.ref = l.ref
      LEFT JOIN locations loc ON loc.id = l.location_id
      WHERE l.reason = 'PICK'
      GROUP BY 1,2,3
    )
    SELECT
      dp.day,
      COALESCE(p.warehouse_id, 0)                  AS warehouse_id,
      COALESCE(dp.platform, 'UNKNOWN')             AS platform,
      COALESCE(o.orders_created, 0)::bigint        AS orders_created,
      COALESCE(s.ship_commits,   0)::bigint        AS ship_commits,
      COALESCE(p.pick_qty,       0)::numeric       AS pick_qty
    FROM (
      SELECT day, platform FROM orders
      UNION
      SELECT day, platform FROM ships
      UNION
      SELECT day, platform FROM picks
    ) dp
    LEFT JOIN orders o ON o.day=dp.day AND o.platform=dp.platform
    LEFT JOIN ships  s ON s.day=dp.day AND s.platform=dp.platform
    LEFT JOIN picks  p ON p.day=dp.day AND p.platform=dp.platform
    ORDER BY day DESC, platform, warehouse_id;
    """
    bind.execute(sa.text(view_sql))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP VIEW IF EXISTS vw_outbound_metrics"))
