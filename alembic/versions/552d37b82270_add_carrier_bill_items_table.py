"""add_carrier_bill_items_table

Revision ID: 552d37b82270
Revises: a39b757e073a
Create Date: 2026-03-15 00:07:46.623381
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "552d37b82270"
down_revision: Union[str, Sequence[str], None] = "a39b757e073a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "carrier_bill_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("import_batch_no", sa.String(length=64), nullable=False),
        sa.Column("carrier_code", sa.String(length=32), nullable=False),
        sa.Column("bill_month", sa.String(length=16), nullable=True),
        sa.Column("tracking_no", sa.String(length=128), nullable=False),
        sa.Column("business_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("destination_province", sa.String(length=64), nullable=True),
        sa.Column("destination_city", sa.String(length=64), nullable=True),
        sa.Column("billing_weight_kg", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("freight_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("surcharge_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("settlement_object", sa.String(length=128), nullable=True),
        sa.Column("order_customer", sa.String(length=128), nullable=True),
        sa.Column("sender_name", sa.String(length=128), nullable=True),
        sa.Column("network_name", sa.String(length=128), nullable=True),
        sa.Column("size_text", sa.String(length=128), nullable=True),
        sa.Column("parent_customer", sa.String(length=128), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="carrier_bill_items_pkey"),
    )

    op.create_index(
        "ix_carrier_bill_items_batch_no",
        "carrier_bill_items",
        ["import_batch_no"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_bill_items_tracking_no",
        "carrier_bill_items",
        ["tracking_no"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_bill_items_carrier_tracking",
        "carrier_bill_items",
        ["carrier_code", "tracking_no"],
        unique=False,
    )
    op.create_index(
        "ix_carrier_bill_items_business_time",
        "carrier_bill_items",
        ["business_time"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_carrier_bill_items_business_time", table_name="carrier_bill_items")
    op.drop_index("ix_carrier_bill_items_carrier_tracking", table_name="carrier_bill_items")
    op.drop_index("ix_carrier_bill_items_tracking_no", table_name="carrier_bill_items")
    op.drop_index("ix_carrier_bill_items_batch_no", table_name="carrier_bill_items")
    op.drop_table("carrier_bill_items")
