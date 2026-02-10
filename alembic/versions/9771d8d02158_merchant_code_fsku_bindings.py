"""merchant_code_fsku_bindings

Revision ID: 9771d8d02158
Revises: 94cd680e8b72
Create Date: 2026-02-10 14:00:45.707985

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9771d8d02158"
down_revision: Union[str, Sequence[str], None] = "94cd680e8b72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 幂等：如果表已存在，直接短路（避免 dev 库被手工建过导致迁移失败）
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = 'merchant_code_fsku_bindings'"
        )
    ).first()
    if exists:
        return

    op.create_table(
        "merchant_code_fsku_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("merchant_code", sa.String(length=128), nullable=False),
        sa.Column(
            "fsku_id",
            sa.Integer(),
            sa.ForeignKey("fskus.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_mc_fsku_bindings_lookup",
        "merchant_code_fsku_bindings",
        ["platform", "shop_id", "merchant_code", "effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_mc_fsku_bindings_fsku_id",
        "merchant_code_fsku_bindings",
        ["fsku_id"],
        unique=False,
    )

    # current 唯一：同一 (platform, shop_id, merchant_code) 只能有一个 effective_to IS NULL
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX ux_mc_fsku_bindings_current "
            "ON merchant_code_fsku_bindings(platform, shop_id, merchant_code) "
            "WHERE effective_to IS NULL"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ux_mc_fsku_bindings_current"))
    op.drop_index("ix_mc_fsku_bindings_fsku_id", table_name="merchant_code_fsku_bindings")
    op.drop_index("ix_mc_fsku_bindings_lookup", table_name="merchant_code_fsku_bindings")
    op.drop_table("merchant_code_fsku_bindings")
