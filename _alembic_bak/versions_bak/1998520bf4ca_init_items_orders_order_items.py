"""init items/orders/order_items

Revision ID: 1998520bf4ca
Revises: bff1b7c009fd
Create Date: 2025-10-05 21:32:34.787217

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "1998520bf4ca"
down_revision: str | Sequence[str] | None = "bff1b7c009fd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
