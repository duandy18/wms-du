"""support multi option item attributes

Revision ID: efbbba76f264
Revises: 13fcf267f60e
Create Date: 2026-04-30

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "efbbba76f264"
down_revision: Union[str, Sequence[str], None] = "13fcf267f60e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow OPTION item attributes to store multiple selected options."""

    op.drop_constraint(
        "uq_item_attribute_values_item_def",
        "item_attribute_values",
        type_="unique",
    )

    op.create_index(
        "uq_item_attribute_values_item_def_scalar",
        "item_attribute_values",
        ["item_id", "attribute_def_id"],
        unique=True,
        postgresql_where="value_option_id IS NULL",
    )

    op.create_index(
        "uq_item_attribute_values_item_def_option",
        "item_attribute_values",
        ["item_id", "attribute_def_id", "value_option_id"],
        unique=True,
        postgresql_where="value_option_id IS NOT NULL",
    )


def downgrade() -> None:
    """Restore one row per item + attribute definition."""

    op.drop_index(
        "uq_item_attribute_values_item_def_option",
        table_name="item_attribute_values",
    )
    op.drop_index(
        "uq_item_attribute_values_item_def_scalar",
        table_name="item_attribute_values",
    )

    op.create_unique_constraint(
        "uq_item_attribute_values_item_def",
        "item_attribute_values",
        ["item_id", "attribute_def_id"],
    )
