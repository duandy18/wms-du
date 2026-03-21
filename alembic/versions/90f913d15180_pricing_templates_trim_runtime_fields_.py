"""pricing_templates: trim runtime fields add validation_status

Revision ID: 90f913d15180
Revises: b279c48eecab
Create Date: 2026-03-21 17:03:00.422280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "90f913d15180"
down_revision: Union[str, Sequence[str], None] = "b279c48eecab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "shipping_provider_pricing_templates"


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        TABLE,
        sa.Column(
            "validation_status",
            sa.String(length=16),
            nullable=False,
            server_default="not_validated",
        ),
    )

    op.create_check_constraint(
        "ck_sppt_validation_status",
        TABLE,
        "validation_status in ('not_validated','passed','failed')",
    )

    op.create_check_constraint(
        "ck_sppt_archived_state_consistent",
        TABLE,
        """
        (status = 'draft' AND archived_at IS NULL)
        OR
        (status = 'archived' AND archived_at IS NOT NULL)
        """,
    )

    op.create_index(
        "ix_shipping_provider_pricing_templates_shipping_provider_id",
        TABLE,
        ["shipping_provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_shipping_provider_pricing_templates_status",
        TABLE,
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_shipping_provider_pricing_templates_validation_status",
        TABLE,
        ["validation_status"],
        unique=False,
    )

    op.drop_constraint("ck_sppt_billable_strategy", TABLE, type_="check")
    op.drop_constraint("ck_sppt_rounding_mode", TABLE, type_="check")
    op.drop_constraint("ck_sppt_default_pricing_mode", TABLE, type_="check")

    op.drop_column(TABLE, "currency")
    op.drop_column(TABLE, "effective_from")
    op.drop_column(TABLE, "effective_to")
    op.drop_column(TABLE, "default_pricing_mode")
    op.drop_column(TABLE, "billable_weight_strategy")
    op.drop_column(TABLE, "volume_divisor")
    op.drop_column(TABLE, "rounding_mode")
    op.drop_column(TABLE, "rounding_step_kg")
    op.drop_column(TABLE, "min_billable_weight_kg")

    op.alter_column(
        TABLE,
        "validation_status",
        server_default=None,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        TABLE,
        sa.Column(
            "min_billable_weight_kg",
            sa.Numeric(precision=10, scale=3),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "rounding_step_kg",
            sa.Numeric(precision=10, scale=3),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "rounding_mode",
            sa.String(length=16),
            nullable=False,
            server_default="none",
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "volume_divisor",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "billable_weight_strategy",
            sa.String(length=32),
            nullable=False,
            server_default="actual_only",
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "default_pricing_mode",
            sa.String(length=32),
            nullable=False,
            server_default="linear_total",
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "effective_to",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        TABLE,
        sa.Column(
            "currency",
            sa.String(length=8),
            nullable=False,
            server_default="CNY",
        ),
    )

    op.create_check_constraint(
        "ck_sppt_default_pricing_mode",
        TABLE,
        "default_pricing_mode in ('flat','linear_total','step_over','manual_quote')",
    )
    op.create_check_constraint(
        "ck_sppt_rounding_mode",
        TABLE,
        "rounding_mode in ('none','ceil')",
    )
    op.create_check_constraint(
        "ck_sppt_billable_strategy",
        TABLE,
        "billable_weight_strategy in ('actual_only','max_actual_volume')",
    )

    op.drop_index(
        "ix_shipping_provider_pricing_templates_validation_status",
        table_name=TABLE,
    )
    op.drop_index(
        "ix_shipping_provider_pricing_templates_status",
        table_name=TABLE,
    )
    op.drop_index(
        "ix_shipping_provider_pricing_templates_shipping_provider_id",
        table_name=TABLE,
    )

    op.drop_constraint("ck_sppt_archived_state_consistent", TABLE, type_="check")
    op.drop_constraint("ck_sppt_validation_status", TABLE, type_="check")
    op.drop_column(TABLE, "validation_status")
