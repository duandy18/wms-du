"""add uq on orders(platform, platform_order_id)

Revision ID: 832986a6185f
Revises: 495074aac8bf
Create Date: 2025-10-05 19:54:55.050271

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "832986a6185f"
down_revision: str | Sequence[str] | None = "495074aac8bf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
