"""datafix: recalc PO status by base units

Revision ID: 2bb34905ead3
Revises: d959e5cde055
Create Date: 2026-01-14 16:32:17.815972

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2bb34905ead3"
down_revision: Union[str, Sequence[str], None] = "d959e5cde055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    数据修复：按 base 口径重算采购单/采购行状态

    当前口径约定（你们系统现状）：
    - purchase_order_lines.qty_ordered: 采购单位（件/箱）
    - purchase_order_lines.units_per_case: 换算因子（每采购单位包含的最小单位数）
    - purchase_order_lines.qty_received: 最小单位（base units）

    因此：
    ordered_base  = qty_ordered * coalesce(nullif(units_per_case,0),1)
    received_base = coalesce(qty_received,0)

    行状态：
    - received_base <= 0 -> CREATED
    - received_base < ordered_base -> PARTIAL
    - received_base >= ordered_base -> RECEIVED
      （允许历史数据中出现 received_base > ordered_base 的情况，仍归为 RECEIVED，避免把脏状态写成 CLOSED）

    头状态：
    - all_zero -> CREATED (closed_at = NULL)
    - all_full -> RECEIVED (closed_at 保留或补齐 NOW())
    - otherwise -> PARTIAL (closed_at = NULL)
    """
    bind = op.get_bind()

    # 1) 重算 purchase_order_lines.status（按 base 口径）
    bind.execute(
        sa.text(
            """
            UPDATE purchase_order_lines pol
               SET status = CASE
                 WHEN COALESCE(pol.qty_received, 0) <= 0 THEN 'CREATED'
                 WHEN COALESCE(pol.qty_received, 0) < (
                      pol.qty_ordered * COALESCE(NULLIF(pol.units_per_case, 0), 1)
                 ) THEN 'PARTIAL'
                 ELSE 'RECEIVED'
               END
            """
        )
    )

    # 2) 重算 purchase_orders.status / closed_at（按行聚合 base 口径）
    bind.execute(
        sa.text(
            """
            WITH agg AS (
              SELECT
                po_id,
                BOOL_AND(COALESCE(qty_received,0) = 0) AS all_zero,
                BOOL_AND(
                  COALESCE(qty_received,0) >= (
                    qty_ordered * COALESCE(NULLIF(units_per_case,0), 1)
                  )
                ) AS all_full
              FROM purchase_order_lines
              GROUP BY po_id
            )
            UPDATE purchase_orders po
               SET status = CASE
                 WHEN agg.all_zero THEN 'CREATED'
                 WHEN agg.all_full THEN 'RECEIVED'
                 ELSE 'PARTIAL'
               END,
                   closed_at = CASE
                     WHEN agg.all_full THEN COALESCE(po.closed_at, NOW())
                     ELSE NULL
                   END
              FROM agg
             WHERE po.id = agg.po_id
            """
        )
    )

    # 3) 边界：没有任何行的采购单，强制回到 CREATED
    bind.execute(
        sa.text(
            """
            UPDATE purchase_orders po
               SET status = 'CREATED',
                   closed_at = NULL
             WHERE NOT EXISTS (
               SELECT 1 FROM purchase_order_lines pol
                WHERE pol.po_id = po.id
             )
            """
        )
    )


def downgrade() -> None:
    """
    数据修复迁移：不可逆（无法可靠恢复“历史错误状态”）。
    downgrade 做 no-op。
    """
    return
