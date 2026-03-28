"""add_taobao_app_configs

Revision ID: b84cdeeaf362
Revises: 2b0d9a228fe4
Create Date: 2026-03-28 16:09:43.023316

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b84cdeeaf362"
down_revision: Union[str, Sequence[str], None] = "2b0d9a228fe4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRIGGER_FUNCTION_NAME = "set_updated_at_timestamp"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "taobao_app_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("app_key", sa.String(length=128), nullable=False),
        sa.Column("app_secret", sa.Text(), nullable=False),
        sa.Column("callback_url", sa.String(length=512), nullable=False),
        sa.Column(
            "api_base_url",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("'https://eco.taobao.com/router/rest'"),
        ),
        sa.Column(
            "sign_method",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'md5'"),
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
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
    )

    op.create_index(
        "ix_taobao_app_configs_is_enabled",
        "taobao_app_configs",
        ["is_enabled"],
        unique=False,
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_taobao_app_configs_enabled_true
        ON taobao_app_configs (is_enabled)
        WHERE is_enabled = true
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_taobao_app_configs_set_updated_at
        ON taobao_app_configs
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER trg_taobao_app_configs_set_updated_at
        BEFORE UPDATE ON taobao_app_configs
        FOR EACH ROW
        EXECUTE FUNCTION {TRIGGER_FUNCTION_NAME}()
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_taobao_app_configs_set_updated_at
        ON taobao_app_configs
        """
    )
    op.drop_index("uq_taobao_app_configs_enabled_true", table_name="taobao_app_configs")
    op.drop_index("ix_taobao_app_configs_is_enabled", table_name="taobao_app_configs")
    op.drop_table("taobao_app_configs")
