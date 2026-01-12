"""drop ck_ledger_delta_nonzero

Revision ID: 433e13d88ae2
Revises: a90e5f62adb7
Create Date: 2026-01-10 12:02:18.715172
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "433e13d88ae2"
down_revision: Union[str, Sequence[str], None] = "a90e5f62adb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    取消台账 delta != 0 的约束。

    语义说明（合同级）：
    - stock_ledger 作为“作业事件流水账”，允许 delta = 0；
    - delta = 0 通常用于：
        * 盘点确认无差异（COUNT_ADJUST）
        * 作业确认类事件（审计留痕）
    - 统计 / 对账口径如需排除 0，应在查询层处理，而不是 DB 强制。
    """
    op.drop_constraint(
        "ck_ledger_delta_nonzero",
        "stock_ledger",
        type_="check",
    )


def downgrade() -> None:
    """
    回滚：恢复 delta != 0 的约束。
    """
    op.create_check_constraint(
        "ck_ledger_delta_nonzero",
        "stock_ledger",
        sa.text("delta <> 0"),
    )
