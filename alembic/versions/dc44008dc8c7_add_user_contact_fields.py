"""add_user_contact_fields

Revision ID: dc44008dc8c7
Revises: 6c9c080ec419
Create Date: 2025-11-27 12:17:28.002090
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "dc44008dc8c7"
down_revision: Union[str, Sequence[str], None] = "6c9c080ec419"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add full_name / phone / email columns to users."""
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("phone", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema: drop full_name / phone / email columns."""
    op.drop_column("users", "email")
    op.drop_column("users", "phone")
    op.drop_column("users", "full_name")
