"""count_doc_add_counted_by_and_reviewed_by_name_snapshots

Revision ID: 542f42d229fa
Revises: 20260422174415
Create Date: 2026-04-23 18:51:09.057446

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "542f42d229fa"
down_revision: Union[str, Sequence[str], None] = "20260422174415"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "count_docs",
        sa.Column(
            "counted_by_name_snapshot",
            sa.String(length=128),
            nullable=True,
            comment="盘点人名字快照",
        ),
    )
    op.add_column(
        "count_docs",
        sa.Column(
            "reviewed_by_name_snapshot",
            sa.String(length=128),
            nullable=True,
            comment="复核人名字快照",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("count_docs", "reviewed_by_name_snapshot")
    op.drop_column("count_docs", "counted_by_name_snapshot")
