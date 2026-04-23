"""count_doc_drop_unused_line_fields_for_execution_page

Revision ID: deb61de57b7b
Revises: 542f42d229fa
Create Date: 2026-04-23 23:56:55.485137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "deb61de57b7b"
down_revision: Union[str, Sequence[str], None] = "542f42d229fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_count_doc_lines_reason_code", table_name="count_doc_lines")
    op.drop_index("ix_count_doc_lines_disposition", table_name="count_doc_lines")

    op.drop_column("count_doc_lines", "reason_code")
    op.drop_column("count_doc_lines", "disposition")
    op.drop_column("count_doc_lines", "remark")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "count_doc_lines",
        sa.Column("remark", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "count_doc_lines",
        sa.Column("disposition", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "count_doc_lines",
        sa.Column("reason_code", sa.String(length=32), nullable=True),
    )

    op.create_index(
        "ix_count_doc_lines_disposition",
        "count_doc_lines",
        ["disposition"],
        unique=False,
    )
    op.create_index(
        "ix_count_doc_lines_reason_code",
        "count_doc_lines",
        ["reason_code"],
        unique=False,
    )
