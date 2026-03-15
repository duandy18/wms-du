"""shipping_records_add_reconcile_fields

Revision ID: 659e5b5bc318
Revises: 552d37b82270
Create Date: 2026-03-15 01:14:18.543478
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "659e5b5bc318"
down_revision: Union[str, Sequence[str], None] = "552d37b82270"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add reconcile fields to shipping_records."""

    op.add_column(
        "shipping_records",
        sa.Column("billing_weight_kg", sa.Numeric(precision=10, scale=3), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("freight_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("surcharge_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("weight_diff_kg", sa.Numeric(precision=10, scale=3), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("cost_diff", sa.Numeric(precision=12, scale=2), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column(
            "reconcile_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'UNMATCHED'"),
        ),
    )

    op.add_column(
        "shipping_records",
        sa.Column("carrier_bill_item_id", sa.BigInteger(), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "shipping_records",
        sa.Column("reconcile_note", sa.String(length=512), nullable=True),
    )

    op.create_foreign_key(
        "fk_shipping_records_carrier_bill_item_id",
        "shipping_records",
        "carrier_bill_items",
        ["carrier_bill_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_shipping_records_reconcile_status",
        "shipping_records",
        ["reconcile_status"],
        unique=False,
    )

    op.alter_column(
        "shipping_records",
        "reconcile_status",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_shipping_records_reconcile_status",
        table_name="shipping_records",
    )

    op.drop_constraint(
        "fk_shipping_records_carrier_bill_item_id",
        "shipping_records",
        type_="foreignkey",
    )

    op.drop_column("shipping_records", "reconcile_note")
    op.drop_column("shipping_records", "reconciled_at")
    op.drop_column("shipping_records", "carrier_bill_item_id")
    op.drop_column("shipping_records", "reconcile_status")
    op.drop_column("shipping_records", "cost_diff")
    op.drop_column("shipping_records", "weight_diff_kg")
    op.drop_column("shipping_records", "surcharge_amount")
    op.drop_column("shipping_records", "freight_amount")
    op.drop_column("shipping_records", "billing_weight_kg")
