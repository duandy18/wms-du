"""backfill stock_ledger sub_reason for legacy outbound ship rows

Revision ID: b7b55a3a78e1
Revises: d9b8bc792ef3
Create Date: 2026-01-12 11:59:07.565820

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7b55a3a78e1"
down_revision: Union[str, Sequence[str], None] = "d9b8bc792ef3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    仅做“可解释性补全”，不改库存事实字段（delta/after_qty/occurred_at 等）：

    规则（保守、可回滚、幂等）：
    - 只补缺失 sub_reason（NULL 或空串）
    - 只针对“出库扣减事实”：delta < 0 且 reason 属于发运/出库类
      reason ∈ {SHIP, SHIPMENT, OUTBOUND_SHIP, OUTBOUND_COMMIT}
    - 将 sub_reason 补为 ORDER_SHIP
    """
    op.execute(
        sa.text(
            """
            UPDATE stock_ledger
               SET sub_reason = 'ORDER_SHIP'
             WHERE (sub_reason IS NULL OR btrim(sub_reason) = '')
               AND delta < 0
               AND upper(coalesce(reason, '')) IN ('SHIP', 'SHIPMENT', 'OUTBOUND_SHIP', 'OUTBOUND_COMMIT')
            """
        )
    )


def downgrade() -> None:
    """
    回滚策略（谨慎）：
    - 仅回滚本迁移写入的 sub_reason 值：ORDER_SHIP -> NULL
    - 不做更复杂的“只回滚某一批行”的精确追踪（当前数据量小且目的明确）。
    """
    op.execute(
        sa.text(
            """
            UPDATE stock_ledger
               SET sub_reason = NULL
             WHERE sub_reason = 'ORDER_SHIP'
            """
        )
    )
