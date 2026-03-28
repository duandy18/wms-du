"""add_store_platform_access_tables

Revision ID: 23a116913711
Revises: a15e25623207
Create Date: 2026-03-28 13:45:50.146814

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "23a116913711"
down_revision: Union[str, Sequence[str], None] = "a15e25623207"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    return table_name in insp.get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    indexes = insp.get_indexes(table_name)
    return any(idx.get("name") == index_name for idx in indexes)


def upgrade() -> None:
    """Upgrade schema."""
    if not _has_table("store_platform_credentials"):
        op.create_table(
            "store_platform_credentials",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("store_id", sa.BigInteger(), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column(
                "credential_type",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'oauth'"),
            ),
            sa.Column("access_token", sa.Text(), nullable=False),
            sa.Column("refresh_token", sa.Text(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("scope", sa.String(length=255), nullable=True),
            sa.Column(
                "raw_payload_json",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'::json"),
            ),
            sa.Column("granted_identity_type", sa.String(length=64), nullable=True),
            sa.Column("granted_identity_value", sa.String(length=128), nullable=True),
            sa.Column("granted_identity_display", sa.String(length=255), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["store_id"],
                ["stores.id"],
                name="fk_store_platform_credentials_store_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "store_id",
                "platform",
                name="uq_store_platform_credentials_store_platform",
            ),
        )

    if not _has_index("store_platform_credentials", "ix_store_platform_credentials_platform"):
        op.create_index(
            "ix_store_platform_credentials_platform",
            "store_platform_credentials",
            ["platform"],
            unique=False,
        )

    if not _has_index("store_platform_credentials", "ix_store_platform_credentials_expires_at"):
        op.create_index(
            "ix_store_platform_credentials_expires_at",
            "store_platform_credentials",
            ["expires_at"],
            unique=False,
        )

    if not _has_table("store_platform_connections"):
        op.create_table(
            "store_platform_connections",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
            sa.Column("store_id", sa.BigInteger(), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column(
                "auth_source",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'none'"),
            ),
            sa.Column(
                "connection_status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'not_connected'"),
            ),
            sa.Column(
                "credential_status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'missing'"),
            ),
            sa.Column(
                "reauth_required",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "pull_ready",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "status",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'not_connected'"),
            ),
            sa.Column("status_reason", sa.String(length=128), nullable=True),
            sa.Column("last_authorized_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_pull_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["store_id"],
                ["stores.id"],
                name="fk_store_platform_connections_store_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "store_id",
                "platform",
                name="uq_store_platform_connections_store_platform",
            ),
        )

    if not _has_index("store_platform_connections", "ix_store_platform_connections_platform"):
        op.create_index(
            "ix_store_platform_connections_platform",
            "store_platform_connections",
            ["platform"],
            unique=False,
        )

    if not _has_index("store_platform_connections", "ix_store_platform_connections_status"):
        op.create_index(
            "ix_store_platform_connections_status",
            "store_platform_connections",
            ["status"],
            unique=False,
        )

    if not _has_index("store_platform_connections", "ix_store_platform_connections_pull_ready"):
        op.create_index(
            "ix_store_platform_connections_pull_ready",
            "store_platform_connections",
            ["pull_ready"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    if _has_table("store_platform_connections"):
        if _has_index("store_platform_connections", "ix_store_platform_connections_pull_ready"):
            op.drop_index(
                "ix_store_platform_connections_pull_ready",
                table_name="store_platform_connections",
            )
        if _has_index("store_platform_connections", "ix_store_platform_connections_status"):
            op.drop_index(
                "ix_store_platform_connections_status",
                table_name="store_platform_connections",
            )
        if _has_index("store_platform_connections", "ix_store_platform_connections_platform"):
            op.drop_index(
                "ix_store_platform_connections_platform",
                table_name="store_platform_connections",
            )
        op.drop_table("store_platform_connections")

    if _has_table("store_platform_credentials"):
        if _has_index("store_platform_credentials", "ix_store_platform_credentials_expires_at"):
            op.drop_index(
                "ix_store_platform_credentials_expires_at",
                table_name="store_platform_credentials",
            )
        if _has_index("store_platform_credentials", "ix_store_platform_credentials_platform"):
            op.drop_index(
                "ix_store_platform_credentials_platform",
                table_name="store_platform_credentials",
            )
        op.drop_table("store_platform_credentials")
