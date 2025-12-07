"""20251201_remove_picked_le_req_check.py

Revision ID: 31c45f47cf0a
Revises: f2e764aaa449
Create Date: 2025-12-01 18:35:22.081902
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31c45f47cf0a'
down_revision: Union[str, Sequence[str], None] = 'f2e764aaa449'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop picked_qty <= req_qty check constraint."""
    op.drop_constraint(
        "pick_task_lines_check",
        "pick_task_lines",
        type_="check",
    )


def downgrade() -> None:
    """Restore picked_qty <= req_qty check constraint."""
    op.create_check_constraint(
        "pick_task_lines_check",
        "pick_task_lines",
        sa.text("picked_qty <= req_qty"),
    )
