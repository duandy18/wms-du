"""add company_code and resource_code to shipping_providers

Revision ID: 932bc7ebb117
Revises: f9199b55771b
Create Date: 2026-03-26 15:17:06.879209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "932bc7ebb117"
down_revision: Union[str, Sequence[str], None] = "f9199b55771b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "shipping_providers",
        sa.Column("company_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "shipping_providers",
        sa.Column("resource_code", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("shipping_providers", "resource_code")
    op.drop_column("shipping_providers", "company_code")
