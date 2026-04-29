"""pms_item_sku_codes_governance

Revision ID: b6d3e914a8c2
Revises: a52459bdb9ed
Create Date: 2026-04-29 18:40:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b6d3e914a8c2"
down_revision: Union[str, Sequence[str], None] = "a52459bdb9ed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "item_sku_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("code_type", sa.String(length=16), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_item_sku_codes_code_non_empty"),
        sa.CheckConstraint(
            "code_type in ('PRIMARY', 'ALIAS', 'LEGACY', 'MANUAL')",
            name="ck_item_sku_codes_code_type",
        ),
        sa.CheckConstraint(
            "(is_primary = false) OR (is_active = true)",
            name="ck_item_sku_codes_primary_active",
        ),
        sa.CheckConstraint(
            "(is_primary = false) OR (effective_to IS NULL)",
            name="ck_item_sku_codes_primary_no_effective_to",
        ),
        sa.CheckConstraint(
            "((code_type = 'PRIMARY') = (is_primary = true))",
            name="ck_item_sku_codes_primary_type_matches_flag",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_item_sku_codes_item",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_item_sku_codes_code"),
    )

    op.create_index(
        "ix_item_sku_codes_item_id",
        "item_sku_codes",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        "uq_item_sku_codes_one_primary_per_item",
        "item_sku_codes",
        ["item_id"],
        unique=True,
        postgresql_where=sa.text("is_primary = true"),
    )

    # Backfill：现有 items.sku 全部成为当前 PRIMARY 编码。
    op.execute(
        """
        INSERT INTO item_sku_codes (
          item_id,
          code,
          code_type,
          is_primary,
          is_active,
          effective_from,
          effective_to,
          remark,
          created_at,
          updated_at
        )
        SELECT
          i.id,
          upper(trim(i.sku)),
          'PRIMARY',
          TRUE,
          TRUE,
          COALESCE(i.created_at, CURRENT_TIMESTAMP),
          NULL,
          'backfilled from items.sku',
          CURRENT_TIMESTAMP,
          CURRENT_TIMESTAMP
        FROM items i
        WHERE trim(i.sku) <> ''
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("uq_item_sku_codes_one_primary_per_item", table_name="item_sku_codes")
    op.drop_index("ix_item_sku_codes_item_id", table_name="item_sku_codes")
    op.drop_table("item_sku_codes")
