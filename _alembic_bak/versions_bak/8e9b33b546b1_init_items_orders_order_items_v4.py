"""init items/orders/order_items v4

Revision ID: 8e9b33b546b1
Revises: 1998520bf4ca
Create Date: 2025-10-05 21:53:28.761427

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "8e9b33b546b1"
down_revision: str | Sequence[str] | None = "1998520bf4ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
