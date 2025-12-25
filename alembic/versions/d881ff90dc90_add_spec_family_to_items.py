"""add spec_family to items

Revision ID: d881ff90dc90
Revises: a42d00f16f1f
Create Date: 2025-12-12 17:08:21.144343
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d881ff90dc90"
down_revision: Union[str, Sequence[str], None] = "a42d00f16f1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add items.spec_family.

    Strategy:
    - Add column as NOT NULL with a temporary server_default='GENERAL' to backfill existing rows.
    - Create an index for filtering/reporting.
    - Drop the server_default so future inserts must explicitly set it (or rely on app-level default).
      (Keeping it NULL-forbidden ensures data quality.)
    """
    op.add_column(
        "items",
        sa.Column(
            "spec_family",
            sa.String(length=32),
            nullable=False,
            server_default="GENERAL",
            comment="规格族：驱动收货/批次/到期/计量等规则（默认 GENERAL）",
        ),
    )

    op.create_index("ix_items_spec_family", "items", ["spec_family"])

    # remove server_default after backfill
    op.alter_column("items", "spec_family", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_items_spec_family", table_name="items")
    op.drop_column("items", "spec_family")
