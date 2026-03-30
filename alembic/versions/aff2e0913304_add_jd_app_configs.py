"""add jd_app_configs

Revision ID: aff2e0913304
Revises: ae9d15268b17
Create Date: 2026-03-30 16:46:03.080465

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "aff2e0913304"
down_revision: Union[str, Sequence[str], None] = "ae9d15268b17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "jd_app_configs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=False),
        sa.Column("callback_url", sa.String(length=512), nullable=False),
        sa.Column(
            "gateway_url",
            sa.String(length=512),
            nullable=False,
            server_default=sa.text("'https://api.jd.com/routerjson'"),
        ),
        sa.Column(
            "sign_method",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'md5'"),
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_jd_app_configs_is_enabled",
        "jd_app_configs",
        ["is_enabled"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_jd_app_configs_is_enabled", table_name="jd_app_configs")
    op.drop_table("jd_app_configs")
