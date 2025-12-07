"""phase_3_7_create_vw_outbound_metrics_v2

Revision ID: e0c9c01ced40
Revises: 7b4bd5845884
Create Date: 2025-11-16 12:58:09.361727

v2 出库 metrics 视图定义：

- 基于：
    * audit_events (OUTBOUND.ORDER_CREATED / OUTBOUND.SHIP_COMMIT)
    * stock_ledger (PICK / OUTBOUND_V2_SHIP / OUTBOUND_SHIP / SHIP)
- 维度：
    * day (UTC 日期)
    * warehouse_id
    * platform
- 指标：
    * orders_created
    * ship_commits
    * pick_qty
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e0c9c01ced40"
down_revision: Union[str, Sequence[str], None] = "7b4bd5845884"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create vw_outbound_metrics view based on outbound v2 + audit + ledger."""
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE VIEW vw_outbound_metrics AS
            WITH agg_orders AS (
                SELECT
                    (ae.created_at AT TIME ZONE 'utc')::date AS day,
                    COALESCE(ae.meta->>'platform', 'UNKNOWN') AS platform,
                    COUNT(*) FILTER (WHERE ae.meta->>'event' = 'ORDER_CREATED') AS orders_created,
                    COUNT(*) FILTER (WHERE ae.meta->>'event' = 'SHIP_COMMIT')   AS ship_commits
                FROM audit_events ae
                WHERE ae.category = 'OUTBOUND'
                GROUP BY day, platform
            ),
            agg_picks AS (
                SELECT
                    (COALESCE(l.occurred_at, l.created_at) AT TIME ZONE 'utc')::date AS day,
                    l.warehouse_id,
                    COALESCE(
                        (
                            SELECT ae.meta->>'platform'
                            FROM audit_events ae
                            WHERE ae.category = 'OUTBOUND'
                              AND ae.ref = l.ref
                            ORDER BY ae.created_at DESC
                            LIMIT 1
                        ),
                        'UNKNOWN'
                    ) AS platform,
                    SUM(-l.delta) AS pick_qty
                FROM stock_ledger l
                WHERE l.delta < 0
                  AND l.reason IN (
                      'PICK',
                      'OUTBOUND_V2_SHIP',
                      'OUTBOUND_SHIP',
                      'SHIP'
                  )
                GROUP BY day, l.warehouse_id, platform
            )
            SELECT
                COALESCE(p.day, o.day)          AS day,
                p.warehouse_id                  AS warehouse_id,
                COALESCE(p.platform, o.platform, 'UNKNOWN') AS platform,
                COALESCE(o.orders_created, 0)   AS orders_created,
                COALESCE(o.ship_commits, 0)     AS ship_commits,
                COALESCE(p.pick_qty, 0)         AS pick_qty
            FROM agg_picks p
            FULL OUTER JOIN agg_orders o
              ON o.day = p.day
             AND o.platform = p.platform
            ;
            """
        )
    )


def downgrade() -> None:
    """Drop vw_outbound_metrics view."""
    op.execute(sa.text("DROP VIEW IF EXISTS vw_outbound_metrics"))
