"""merge heads after cleanup

Revision ID: 20251112_merge_after_cleanup
Revises: 20251110_batches_drop_legacy_dates, 20251112_drop_unused_indexes
Create Date: 2025-11-09 13:26:23.106315

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "20251112_merge_after_cleanup"
down_revision: Union[str, Sequence[str], None] = (
    "20251110_batches_drop_legacy_dates",
    "20251112_drop_unused_indexes",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
