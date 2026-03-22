"""pricing_template_validation_records

Revision ID: ac6aa54a55e6
Revises: 9ce40c188f6b
Create Date: 2026-03-22 13:57:42.835887
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ac6aa54a55e6"
down_revision: Union[str, Sequence[str], None] = "9ce40c188f6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shipping_provider_pricing_template_validation_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("operator_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["shipping_provider_pricing_templates.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_index(
        "ix_sppt_validation_records_template_id",
        "shipping_provider_pricing_template_validation_records",
        ["template_id"],
        unique=False,
    )

    op.create_index(
        "ix_sppt_validation_records_operator_user_id",
        "shipping_provider_pricing_template_validation_records",
        ["operator_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sppt_validation_records_operator_user_id",
        table_name="shipping_provider_pricing_template_validation_records",
    )

    op.drop_index(
        "ix_sppt_validation_records_template_id",
        table_name="shipping_provider_pricing_template_validation_records",
    )

    op.drop_table("shipping_provider_pricing_template_validation_records")
