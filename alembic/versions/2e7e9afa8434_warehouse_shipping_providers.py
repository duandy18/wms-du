"""warehouse_shipping_providers

Revision ID: 2e7e9afa8434
Revises: 53b825c10eaa
Create Date: 2026-01-20 15:17:22.524613

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e7e9afa8434"
down_revision: Union[str, Sequence[str], None] = "53b825c10eaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "warehouse_shipping_providers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("shipping_provider_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("pickup_cutoff_time", sa.String(length=5), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shipping_provider_id"], ["shipping_providers.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "warehouse_id",
            "shipping_provider_id",
            name="uq_wh_shipping_providers_wh_provider",
        ),
    )

    op.create_index(
        "ix_wh_shipping_providers_wh_active",
        "warehouse_shipping_providers",
        ["warehouse_id", "active"],
        unique=False,
    )
    op.create_index(
        "ix_wh_shipping_providers_provider",
        "warehouse_shipping_providers",
        ["shipping_provider_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wh_shipping_providers_provider", table_name="warehouse_shipping_providers")
    op.drop_index("ix_wh_shipping_providers_wh_active", table_name="warehouse_shipping_providers")
    op.drop_table("warehouse_shipping_providers")
