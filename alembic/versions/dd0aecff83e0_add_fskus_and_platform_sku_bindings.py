"""add fskus and platform sku bindings

Revision ID: dd0aecff83e0
Revises: e9eaa9d713c5
Create Date: 2026-02-05 13:51:57.129906

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "dd0aecff83e0"
down_revision: Union[str, Sequence[str], None] = "e9eaa9d713c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # -----------------------
    # fskus
    # -----------------------
    op.create_table(
        "fskus",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("unit_label", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fskus_status", "fskus", ["status"])

    # -----------------------
    # fsku_components
    # -----------------------
    op.create_table(
        "fsku_components",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "fsku_id",
            sa.Integer(),
            sa.ForeignKey("fskus.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("qty", sa.Numeric(18, 6), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fsku_components_fsku_id", "fsku_components", ["fsku_id"])
    op.create_index("ix_fsku_components_item_id", "fsku_components", ["item_id"])

    # -----------------------
    # platform_sku_bindings
    # -----------------------
    op.create_table(
        "platform_sku_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(length=50), nullable=False),
        sa.Column("shop_id", sa.Integer(), nullable=False),
        sa.Column("platform_sku_id", sa.String(length=200), nullable=False),
        sa.Column("fsku_id", sa.Integer(), sa.ForeignKey("fskus.id"), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_platform_sku_bindings_key",
        "platform_sku_bindings",
        ["platform", "shop_id", "platform_sku_id"],
    )
    # ✅ 同 key 同时只能有一条 current（effective_to IS NULL）
    op.create_index(
        "ux_platform_sku_bindings_current",
        "platform_sku_bindings",
        ["platform", "shop_id", "platform_sku_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 反向顺序：先 drop index/table，再回滚依赖
    op.drop_index("ux_platform_sku_bindings_current", table_name="platform_sku_bindings")
    op.drop_index("ix_platform_sku_bindings_key", table_name="platform_sku_bindings")
    op.drop_table("platform_sku_bindings")

    op.drop_index("ix_fsku_components_item_id", table_name="fsku_components")
    op.drop_index("ix_fsku_components_fsku_id", table_name="fsku_components")
    op.drop_table("fsku_components")

    op.drop_index("ix_fskus_status", table_name="fskus")
    op.drop_table("fskus")
