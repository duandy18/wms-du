"""add uq on orders(platform, platform_order_id)

Revision ID: bff1b7c009fd
Revises: 832986a6185f
Create Date: 2025-10-05 19:57:16.318821

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "bff1b7c009fd"
down_revision: str | Sequence[str] | None = "832986a6185f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
