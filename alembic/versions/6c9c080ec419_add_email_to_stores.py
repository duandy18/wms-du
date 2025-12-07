"""add_email_to_stores

Revision ID: 6c9c080ec419
Revises: 8230735fe423
Create Date: 2025-11-27 09:18:54.889142
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6c9c080ec419"
down_revision: Union[str, Sequence[str], None] = "8230735fe423"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add email / contact_name / contact_phone to stores."""

    # email: 可选
    op.add_column(
        "stores",
        sa.Column("email", sa.String(length=255), nullable=True),
    )

    # 联系人（可选）
    op.add_column(
        "stores",
        sa.Column("contact_name", sa.String(length=100), nullable=True),
    )

    # 联系电话（可选）
    op.add_column(
        "stores",
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema by dropping the new columns."""

    op.drop_column("stores", "contact_phone")
    op.drop_column("stores", "contact_name")
    op.drop_column("stores", "email")
