"""add_store_tokens_table

Revision ID: 29480788f1e9
Revises: e21d07741545
Create Date: 2025-11-26 17:51:33.074312

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "29480788f1e9"
down_revision: Union[str, Sequence[str], None] = "e21d07741545"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create store_tokens table (if not exists)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 如果之前已经手工建过表，就直接跳过，避免重复报错
    if "store_tokens" in insp.get_table_names():
        return

    op.create_table(
        "store_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "store_id",
            sa.BigInteger(),
            sa.ForeignKey("stores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("mall_id", sa.String(length=64), nullable=True),
        sa.Column("access_token", sa.String(length=255), nullable=False),
        sa.Column("refresh_token", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
    )

    op.create_index(
        "ix_store_tokens_store_platform",
        "store_tokens",
        ["store_id", "platform"],
    )


def downgrade() -> None:
    """Downgrade schema: drop store_tokens table (if exists)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "store_tokens" not in insp.get_table_names():
        return

    op.drop_index("ix_store_tokens_store_platform", table_name="store_tokens")
    op.drop_table("store_tokens")
