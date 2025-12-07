"""add shipping_records table

Revision ID: 0a720839f121
Revises: 9f4555426904
Create Date: 2025-12-04 09:50:51.622563
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0a720839f121'
down_revision: Union[str, Sequence[str], None] = '9f4555426904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create shipping_records."""
    op.create_table(
        "shipping_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_ref", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=64), nullable=False),
        sa.Column("carrier_code", sa.String(length=32), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),

        sa.Column("weight_kg", sa.Numeric(10, 3), nullable=True),
        sa.Column("cost_estimated", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_real", sa.Numeric(12, 2), nullable=True),

        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_shipping_records_ref_time",
        "shipping_records",
        ["order_ref", "created_at"],
    )

    op.create_index(
        "ix_shipping_records_trace_id",
        "shipping_records",
        ["trace_id"],
    )


def downgrade() -> None:
    """Downgrade schema: drop shipping_records."""
    op.drop_index("ix_shipping_records_trace_id", table_name="shipping_records")
    op.drop_index("ix_shipping_records_ref_time", table_name="shipping_records")
    op.drop_table("shipping_records")
