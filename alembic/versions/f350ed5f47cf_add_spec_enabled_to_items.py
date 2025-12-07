"""add spec & enabled to items

Revision ID: f350ed5f47cf
Revises: af31970de206
Create Date: 2025-11-25 00:41:21.515172
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f350ed5f47cf"
down_revision: Union[str, Sequence[str], None] = "af31970de206"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: add spec/enabled to items, normalize unit default."""

    # 1) 新增 spec 列（规格说明，可空）
    op.add_column(
        "items",
        sa.Column("spec", sa.String(length=128), nullable=True),
    )

    # 2) 新增 enabled 列（是否启用，默认 true）
    op.add_column(
        "items",
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )

    # 3) 确保 unit 的默认值为 'PCS'
    op.alter_column(
        "items",
        "unit",
        existing_type=sa.String(length=8),
        existing_nullable=False,
        server_default=sa.text("'PCS'::character varying"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 回滚时删除 enabled/spec 列；unit 默认值恢复为 NULL（或你之前的状态）
    op.drop_column("items", "enabled")
    op.drop_column("items", "spec")

    op.alter_column(
        "items",
        "unit",
        existing_type=sa.String(length=8),
        existing_nullable=False,
        server_default=None,
    )
