"""harden_shipping_provider_pricing_matrix_shape

Revision ID: ffa019067b26
Revises: d1a2e080a1dc
Create Date: 2026-03-07 13:30:46.064514
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "ffa019067b26"
down_revision: Union[str, Sequence[str], None] = "d1a2e080a1dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "shipping_provider_pricing_matrix"


def _has_check(bind, table_name: str, check_name: str) -> bool:
    sql = text(
        """
        SELECT 1
          FROM information_schema.table_constraints
         WHERE table_name = :table_name
           AND constraint_type = 'CHECK'
           AND constraint_name = :check_name
         LIMIT 1
        """
    )
    row = bind.execute(sql, {"table_name": table_name, "check_name": check_name}).first()
    return row is not None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    for ck_name in (
        "ck_sppm_flat_needs_flat_amount",
        "ck_sppm_linear_needs_rate",
        "ck_sppm_step_over_needs_fields",
        "ck_sppm_flat_shape",
        "ck_sppm_linear_total_shape",
        "ck_sppm_step_over_shape",
        "ck_sppm_manual_quote_shape",
    ):
        if _has_check(bind, TABLE, ck_name):
            op.drop_constraint(ck_name, TABLE, type_="check")

    op.create_check_constraint(
        "ck_sppm_flat_shape",
        TABLE,
        """
        pricing_mode <> 'flat'
        OR (
            flat_amount IS NOT NULL
            AND base_amount IS NULL
            AND rate_per_kg IS NULL
            AND base_kg IS NULL
        )
        """,
    )

    op.create_check_constraint(
        "ck_sppm_linear_total_shape",
        TABLE,
        """
        pricing_mode <> 'linear_total'
        OR (
            flat_amount IS NULL
            AND rate_per_kg IS NOT NULL
            AND base_kg IS NULL
        )
        """,
    )

    op.create_check_constraint(
        "ck_sppm_step_over_shape",
        TABLE,
        """
        pricing_mode <> 'step_over'
        OR (
            flat_amount IS NULL
            AND base_kg IS NOT NULL
            AND base_amount IS NOT NULL
            AND rate_per_kg IS NOT NULL
        )
        """,
    )

    op.create_check_constraint(
        "ck_sppm_manual_quote_shape",
        TABLE,
        """
        pricing_mode <> 'manual_quote'
        OR (
            flat_amount IS NULL
            AND base_amount IS NULL
            AND rate_per_kg IS NULL
            AND base_kg IS NULL
        )
        """,
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    for ck_name in (
        "ck_sppm_flat_shape",
        "ck_sppm_linear_total_shape",
        "ck_sppm_step_over_shape",
        "ck_sppm_manual_quote_shape",
    ):
        if _has_check(bind, TABLE, ck_name):
            op.drop_constraint(ck_name, TABLE, type_="check")

    op.create_check_constraint(
        "ck_sppm_flat_needs_flat_amount",
        TABLE,
        "pricing_mode <> 'flat' OR flat_amount IS NOT NULL",
    )

    op.create_check_constraint(
        "ck_sppm_linear_needs_rate",
        TABLE,
        "pricing_mode <> 'linear_total' OR rate_per_kg IS NOT NULL",
    )

    op.create_check_constraint(
        "ck_sppm_step_over_needs_fields",
        TABLE,
        """
        pricing_mode <> 'step_over'
        OR (
            base_kg IS NOT NULL
            AND base_amount IS NOT NULL
            AND rate_per_kg IS NOT NULL
        )
        """,
    )
