"""merge v1.1: event_occurred_at_default + pick_tasks_tables

Revision ID: 13caaa2af6ea
Revises: 20251101_event_occurred_at_default, 20251101_pick_tasks_tables
Create Date: 2025-11-01 10:30:40.497950

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "13caaa2af6ea"
down_revision: Union[str, Sequence[str], None] = (
    "20251101_event_occurred_at_default",
    "20251101_pick_tasks_tables",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
