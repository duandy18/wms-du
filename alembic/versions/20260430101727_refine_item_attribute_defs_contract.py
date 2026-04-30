"""Refine PMS item attribute definition contract.

Revision ID: 20260430101727
Revises: 20260429233831
Create Date: 2026-04-30

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260430101727"
down_revision: Union[str, Sequence[str], None] = "20260429233831"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "item_attribute_defs",
        sa.Column("selection_mode", sa.String(length=16), server_default="SINGLE", nullable=False),
    )
    op.add_column(
        "item_attribute_defs",
        sa.Column("is_item_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "item_attribute_defs",
        sa.Column("is_sku_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "item_attribute_defs",
        sa.Column("is_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    op.execute(
        """
        UPDATE item_attribute_defs
           SET is_item_required = is_required
        """
    )

    op.execute(
        """
        UPDATE item_attribute_defs
           SET selection_mode = 'MULTI'
         WHERE value_type = 'OPTION'
           AND is_sku_segment IS TRUE
        """
    )

    op.drop_constraint("fk_item_attribute_defs_category", "item_attribute_defs", type_="foreignkey")
    op.drop_constraint("uq_item_attribute_defs_category_code", "item_attribute_defs", type_="unique")
    op.drop_index("ix_item_attribute_defs_category_id", table_name="item_attribute_defs")

    op.drop_column("item_attribute_defs", "category_id")
    op.drop_column("item_attribute_defs", "is_required")
    op.drop_column("item_attribute_defs", "is_searchable")
    op.drop_column("item_attribute_defs", "is_filterable")

    op.create_check_constraint(
        "ck_item_attribute_defs_selection_mode",
        "item_attribute_defs",
        "selection_mode in ('SINGLE', 'MULTI')",
    )
    op.create_unique_constraint(
        "uq_item_attribute_defs_product_kind_code",
        "item_attribute_defs",
        ["product_kind", "code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_item_attribute_defs_product_kind_code", "item_attribute_defs", type_="unique")
    op.drop_constraint("ck_item_attribute_defs_selection_mode", "item_attribute_defs", type_="check")

    op.add_column("item_attribute_defs", sa.Column("is_filterable", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("item_attribute_defs", sa.Column("is_searchable", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("item_attribute_defs", sa.Column("is_required", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.add_column("item_attribute_defs", sa.Column("category_id", sa.Integer(), nullable=True))

    op.execute(
        """
        UPDATE item_attribute_defs
           SET is_required = is_item_required
        """
    )

    op.create_foreign_key(
        "fk_item_attribute_defs_category",
        "item_attribute_defs",
        "pms_business_categories",
        ["category_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_item_attribute_defs_category_code",
        "item_attribute_defs",
        ["category_id", "code"],
    )
    op.create_index("ix_item_attribute_defs_category_id", "item_attribute_defs", ["category_id"])

    op.drop_column("item_attribute_defs", "is_locked")
    op.drop_column("item_attribute_defs", "is_sku_required")
    op.drop_column("item_attribute_defs", "is_item_required")
    op.drop_column("item_attribute_defs", "selection_mode")
