"""expected_counts_to_pricing_templates

Revision ID: 00100b843946
Revises: 162281b73f0d
Create Date: 2026-03-22 17:07:52.599581

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "00100b843946"
down_revision: Union[str, Sequence[str], None] = "162281b73f0d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shipping_provider_pricing_templates",
        sa.Column("expected_ranges_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "shipping_provider_pricing_templates",
        sa.Column("expected_groups_count", sa.Integer(), nullable=True),
    )

    op.execute(
        """
        UPDATE shipping_provider_pricing_templates
           SET expected_ranges_count = 1
         WHERE expected_ranges_count IS NULL
        """
    )
    op.execute(
        """
        UPDATE shipping_provider_pricing_templates
           SET expected_groups_count = 1
         WHERE expected_groups_count IS NULL
        """
    )

    op.alter_column(
        "shipping_provider_pricing_templates",
        "expected_ranges_count",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "shipping_provider_pricing_templates",
        "expected_groups_count",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_sppt_expected_ranges_count_positive",
        "shipping_provider_pricing_templates",
        "expected_ranges_count > 0",
    )
    op.create_check_constraint(
        "ck_sppt_expected_groups_count_positive",
        "shipping_provider_pricing_templates",
        "expected_groups_count > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_sppt_expected_groups_count_positive",
        "shipping_provider_pricing_templates",
        type_="check",
    )
    op.drop_constraint(
        "ck_sppt_expected_ranges_count_positive",
        "shipping_provider_pricing_templates",
        type_="check",
    )

    op.drop_column("shipping_provider_pricing_templates", "expected_groups_count")
    op.drop_column("shipping_provider_pricing_templates", "expected_ranges_count")
