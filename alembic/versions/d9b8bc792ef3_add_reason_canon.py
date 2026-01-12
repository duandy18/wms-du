"""add reason_canon

Revision ID: d9b8bc792ef3
Revises: 433e13d88ae2
Create Date: 2026-01-10 14:01:14.513193

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d9b8bc792ef3"
down_revision: Union[str, Sequence[str], None] = "433e13d88ae2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    增加 reason_canon（稳定口径）：

    - reason: 保留原始/兼容值（参与幂等键，不能强改）
    - reason_canon: 归一后的稳定口径（RECEIPT/SHIPMENT/ADJUSTMENT），用于统计/筛选/UI
    """
    op.add_column(
        "stock_ledger",
        sa.Column("reason_canon", sa.String(length=32), nullable=True),
    )

    op.create_index(
        "ix_stock_ledger_reason_canon",
        "stock_ledger",
        ["reason_canon"],
    )

    op.create_index(
        "ix_stock_ledger_reason_canon_time",
        "stock_ledger",
        ["reason_canon", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_ledger_reason_canon_time", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_reason_canon", table_name="stock_ledger")
    op.drop_column("stock_ledger", "reason_canon")
