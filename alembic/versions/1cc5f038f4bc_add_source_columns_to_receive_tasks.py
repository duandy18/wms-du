"""add source columns to receive_tasks

Revision ID: 1cc5f038f4bc
Revises: a397db6563ad
Create Date: 2025-11-29 19:08:17.698221
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1cc5f038f4bc"
down_revision: Union[str, Sequence[str], None] = "a397db6563ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add source_type/source_id to receive_tasks."""
    op.add_column(
        "receive_tasks",
        sa.Column(
            "source_type",
            sa.String(length=32),
            nullable=False,
            server_default="PO",
        ),
    )
    op.add_column(
        "receive_tasks",
        sa.Column(
            "source_id",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_receive_tasks_source_id",
        "receive_tasks",
        ["source_id"],
    )


def downgrade() -> None:
    """Downgrade schema: drop source_type/source_id."""
    op.drop_index("ix_receive_tasks_source_id", table_name="receive_tasks")
    op.drop_column("receive_tasks", "source_id")
    op.drop_column("receive_tasks", "source_type")
