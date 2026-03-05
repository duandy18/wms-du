"""add archived_at to pricing schemes

Revision ID: 1dc4f9f72d07
Revises: abc28dab3b45
Create Date: 2026-01-26 13:59:21.736278
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1dc4f9f72d07"
down_revision: Union[str, Sequence[str], None] = "abc28dab3b45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shipping_provider_pricing_schemes",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_spps_provider_archived_active",
        "shipping_provider_pricing_schemes",
        ["shipping_provider_id", "archived_at", "active", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_spps_provider_archived_active", table_name="shipping_provider_pricing_schemes")
    op.drop_column("shipping_provider_pricing_schemes", "archived_at")
