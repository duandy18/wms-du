"""init items/orders/order_items v6

Revision ID: 08ca516bcc55
Revises: 8e9b33b546b1
Create Date: 2025-10-05 22:07:21.749952

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "08ca516bcc55"
down_revision: str | Sequence[str] | None = "8e9b33b546b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
