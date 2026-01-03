"""drop priority from shipping pricing schemes/zones/surcharges

Revision ID: bc1a504aa240
Revises: 473f09545f17
Create Date: 2026-01-03 13:31:22.670656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bc1a504aa240"
down_revision: Union[str, Sequence[str], None] = "473f09545f17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Phase B: hard drop priority fields in shipping pricing domain.

    Tables:
      - shipping_provider_pricing_schemes.priority
      - shipping_provider_zones.priority
      - shipping_provider_surcharges.priority

    Also drop related indexes that include priority.
    """

    # 1) drop indexes (must come before dropping columns referenced by them)
    op.drop_index(
        "ix_sp_pricing_schemes_provider_priority",
        table_name="shipping_provider_pricing_schemes",
    )
    op.drop_index(
        "ix_sp_zones_scheme_priority",
        table_name="shipping_provider_zones",
    )
    op.drop_index(
        "ix_sp_surcharges_scheme_priority",
        table_name="shipping_provider_surcharges",
    )

    # 2) drop columns
    op.drop_column("shipping_provider_pricing_schemes", "priority")
    op.drop_column("shipping_provider_zones", "priority")
    op.drop_column("shipping_provider_surcharges", "priority")


def downgrade() -> None:
    """
    Restore priority columns and their indexes.

    NOTE: data restored with server_default=100 and nullable=False,
    matching the original v1 schema.
    """

    # 1) add columns back
    op.add_column(
        "shipping_provider_pricing_schemes",
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )
    op.add_column(
        "shipping_provider_zones",
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )
    op.add_column(
        "shipping_provider_surcharges",
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
    )

    # 2) recreate indexes
    op.create_index(
        "ix_sp_pricing_schemes_provider_priority",
        "shipping_provider_pricing_schemes",
        ["shipping_provider_id", "priority"],
    )
    op.create_index(
        "ix_sp_zones_scheme_priority",
        "shipping_provider_zones",
        ["scheme_id", "priority"],
    )
    op.create_index(
        "ix_sp_surcharges_scheme_priority",
        "shipping_provider_surcharges",
        ["scheme_id", "priority"],
    )
