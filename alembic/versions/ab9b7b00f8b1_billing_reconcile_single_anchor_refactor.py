"""billing_reconcile_single_anchor_refactor

Revision ID: ab9b7b00f8b1
Revises: 9df4f9681144
Create Date: 2026-03-19 13:53:13.562825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ab9b7b00f8b1"
down_revision: Union[str, Sequence[str], None] = "9df4f9681144"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 只做 9df 之后剩余的“单锚点修正”：
    # 1) carrier_bill_item_id 改为 NOT NULL
    # 2) partial unique index -> 普通 unique constraint

    op.drop_index(
        "uq_shipping_record_reconciliations_bill_item_id_notnull",
        table_name="shipping_record_reconciliations",
    )

    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.create_unique_constraint(
        "uq_shipping_record_reconciliations_bill_item_id",
        "shipping_record_reconciliations",
        ["carrier_bill_item_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "uq_shipping_record_reconciliations_bill_item_id",
        "shipping_record_reconciliations",
        type_="unique",
    )

    op.alter_column(
        "shipping_record_reconciliations",
        "carrier_bill_item_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    op.create_index(
        "uq_shipping_record_reconciliations_bill_item_id_notnull",
        "shipping_record_reconciliations",
        ["carrier_bill_item_id"],
        unique=True,
        postgresql_where=sa.text("carrier_bill_item_id IS NOT NULL"),
    )
