"""merge heads after Step6 integration

Revision ID: 6e6459c3169f
Revises: 20251014_add_stock_snapshots, 20251014_perf_indexes, 20251014_uq_batches_composite
Create Date: 2025-10-14 18:50:58.419185

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6e6459c3169f"
down_revision: str | Sequence[str] | None = (
    "20251014_add_stock_snapshots",
    "20251014_perf_indexes",
    "20251014_uq_batches_composite",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
