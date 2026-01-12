"""add sub_reason to stock_ledger

Revision ID: a90e5f62adb7
Revises: 9dd9c977951c
Create Date: 2026-01-10 11:50:30.896224

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a90e5f62adb7"
down_revision: Union[str, Sequence[str], None] = "9dd9c977951c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1) 新增列：sub_reason（业务细分，例如 PO_RECEIPT / RETURN_RECEIPT / ORDER_SHIP / COUNT_ADJUST）
    op.add_column(
        "stock_ledger",
        sa.Column("sub_reason", sa.String(length=32), nullable=True),
    )

    # 2) 索引：按子原因过滤
    op.create_index(
        "ix_stock_ledger_sub_reason",
        "stock_ledger",
        ["sub_reason"],
    )

    # 3) 组合索引：子原因 + 时间（常用筛选窗口）
    op.create_index(
        "ix_stock_ledger_sub_reason_time",
        "stock_ledger",
        ["sub_reason", "occurred_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_stock_ledger_sub_reason_time", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_sub_reason", table_name="stock_ledger")
    op.drop_column("stock_ledger", "sub_reason")
