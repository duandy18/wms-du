"""feat(shipping-provider): add address

Revision ID: a9c1b7827263
Revises: 1dc4f9f72d07
Create Date: 2026-01-26 16:21:28.802810

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a9c1b7827263"
down_revision: Union[str, Sequence[str], None] = "1dc4f9f72d07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("shipping_providers", sa.Column("address", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("shipping_providers", "address")
