"""p41_add_trace_id_to_stock_ledger

Revision ID: d42d5c693371
Revises: 5d114a84c638
Create Date: 2025-11-16 02:30:53.498077
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d42d5c693371"
down_revision: Union[str, Sequence[str], None] = "5d114a84c638"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add trace_id column to stock_ledger and backfill from ref."""

    # 1) 增加 trace_id 列（可空，长度 64 足够放业务 trace key）
    op.add_column(
        "stock_ledger",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    )

    # 2) 回填现有数据：把 ref 的值同步到 trace_id，确保历史数据也能被 trace 命中
    op.execute(
        """
        UPDATE stock_ledger
           SET trace_id = ref
         WHERE trace_id IS NULL
        """
    )

    # 3) 建索引，便于 /debug/trace/{trace_id} 快速按 trace_id 查
    op.create_index(
        "ix_stock_ledger_trace_id",
        "stock_ledger",
        ["trace_id"],
    )


def downgrade() -> None:
    """Remove trace_id column and its index from stock_ledger."""
    op.drop_index("ix_stock_ledger_trace_id", table_name="stock_ledger")
    op.drop_column("stock_ledger", "trace_id")
