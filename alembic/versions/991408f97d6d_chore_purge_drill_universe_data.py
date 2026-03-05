"""chore: purge DRILL universe data

Revision ID: 991408f97d6d
Revises: 58ce95355c9f
Create Date: 2026-02-14 01:42:11.340724

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "991408f97d6d"
down_revision: Union[str, Sequence[str], None] = "58ce95355c9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UNIVERSE_TABLES = [
    # 事实流水（最底层）
    "stock_ledger",
    "stocks",
    "stock_snapshots",
    # 出库/任务
    "outbound_commits_v2",
    "pick_tasks",
    # 订单衍生事实
    "platform_order_addresses",
    # 令牌（如确认为宇宙 scope）
    "store_tokens",
    # 最后删订单头
    "orders",
]


def upgrade() -> None:
    """
    Purge DRILL universe data.

    设计原则：
    - 只删除 scope='DRILL' 的数据；
    - 不触碰 pricing_scheme_dest_adjustments（其 scope 为 province/city 业务含义）；
    - 不修改 schema，仅做数据清理；
    - 按依赖顺序删除，尽量避免 FK 约束问题。
    """
    conn = op.get_bind()

    for tbl in _UNIVERSE_TABLES:
        conn.execute(
            sa.text(f"DELETE FROM {tbl} WHERE scope = 'DRILL'")
        )


def downgrade() -> None:
    """
    Irreversible data purge.

    DRILL 数据被物理删除，无法恢复。
    """
    raise RuntimeError("This migration is irreversible: DRILL universe data has been purged.")
