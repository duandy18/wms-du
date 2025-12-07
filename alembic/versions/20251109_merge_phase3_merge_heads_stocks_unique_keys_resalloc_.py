"""merge heads: stocks_unique_keys + resalloc_partial_unique

Revision ID: 20251109_merge_phase3
Revises: 20251108_stocks_unique_keys, 20251109_resalloc_partial_unique
Create Date: 2025-11-08 21:45:20.623368

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20251109_merge_phase3"
down_revision: Union[str, Sequence[str], None] = (
    "20251108_stocks_unique_keys",
    "20251109_resalloc_partial_unique",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
