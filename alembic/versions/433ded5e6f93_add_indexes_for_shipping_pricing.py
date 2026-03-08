"""add indexes for shipping pricing

Revision ID: 433ded5e6f93
Revises: 35303a753704
Create Date: 2026-03-08 16:36:23.006062
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "433ded5e6f93"
down_revision: Union[str, Sequence[str], None] = "35303a753704"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_index(
        "ix_shipping_provider_destination_groups_scheme_id",
        "shipping_provider_destination_groups",
        ["scheme_id"],
        unique=False,
    )

    op.create_index(
        "ix_shipping_provider_pricing_matrix_group_id",
        "shipping_provider_pricing_matrix",
        ["group_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_shipping_provider_pricing_matrix_group_id",
        table_name="shipping_provider_pricing_matrix",
    )

    op.drop_index(
        "ix_shipping_provider_destination_groups_scheme_id",
        table_name="shipping_provider_destination_groups",
    )
