"""shrink_shipping_records_ledger_fields

Revision ID: 245b131a859b
Revises: a7d1f3d0bf91
Create Date: 2026-03-16 15:10:57

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "245b131a859b"
down_revision: Union[str, Sequence[str], None] = "a7d1f3d0bf91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    将 shipping_records 收敛为“物流台帐表”

    删除字段：
    - trace_id
    - weight_kg
    - cost_real
    - meta
    - packaging_weight_kg
    - delivery_time
    - status
    - error_code
    - error_message
    """

    op.drop_column("shipping_records", "trace_id")
    op.drop_column("shipping_records", "weight_kg")
    op.drop_column("shipping_records", "cost_real")
    op.drop_column("shipping_records", "meta")
    op.drop_column("shipping_records", "packaging_weight_kg")
    op.drop_column("shipping_records", "delivery_time")
    op.drop_column("shipping_records", "status")
    op.drop_column("shipping_records", "error_code")
    op.drop_column("shipping_records", "error_message")


def downgrade() -> None:
    """
    回滚：恢复旧字段
    """

    op.add_column(
        "shipping_records",
        sa.Column("error_message", sa.String(length=512), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("status", sa.String(length=32), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("delivery_time", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("packaging_weight_kg", sa.Numeric(10, 3), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("meta", sa.JSON(), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("cost_real", sa.Numeric(12, 2), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("weight_kg", sa.Numeric(10, 3), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    )
