"""add electronic_waybill_configs table

Revision ID: 6c86cf2f97a7
Revises: 932bc7ebb117
Create Date: 2026-03-26 15:31:56.823037

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6c86cf2f97a7"
down_revision: Union[str, Sequence[str], None] = "932bc7ebb117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "electronic_waybill_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=64), nullable=False),
        sa.Column("shipping_provider_id", sa.Integer(), nullable=False),
        sa.Column("customer_code", sa.String(length=64), nullable=False),
        sa.Column("sender_name", sa.String(length=64), nullable=True),
        sa.Column("sender_mobile", sa.String(length=32), nullable=True),
        sa.Column("sender_phone", sa.String(length=32), nullable=True),
        sa.Column("sender_province", sa.String(length=64), nullable=True),
        sa.Column("sender_city", sa.String(length=64), nullable=True),
        sa.Column("sender_district", sa.String(length=64), nullable=True),
        sa.Column("sender_address", sa.String(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["shipping_provider_id"],
            ["shipping_providers.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "shop_id",
            "shipping_provider_id",
            name="uq_electronic_waybill_configs_platform_shop_provider",
        ),
    )
    op.create_index(
        "ix_electronic_waybill_configs_shipping_provider_id",
        "electronic_waybill_configs",
        ["shipping_provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_electronic_waybill_configs_platform_shop",
        "electronic_waybill_configs",
        ["platform", "shop_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_electronic_waybill_configs_platform_shop", table_name="electronic_waybill_configs")
    op.drop_index("ix_electronic_waybill_configs_shipping_provider_id", table_name="electronic_waybill_configs")
    op.drop_table("electronic_waybill_configs")
