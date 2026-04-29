"""pms_retire_item_test_sets

Revision ID: 0bf1c4ffb51a
Revises: '20260429114500'
Create Date: 2026-04-29

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0bf1c4ffb51a"
down_revision: Union[str, Sequence[str], None] = '20260429114500'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Retire PMS item test sets."""

    op.drop_table("item_test_set_items")
    op.drop_index("ix_item_test_sets_code", table_name="item_test_sets")
    op.drop_table("item_test_sets")


def downgrade() -> None:
    """Restore PMS item test sets."""

    op.create_table(
        "item_test_sets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_item_test_sets_code", "item_test_sets", ["code"], unique=True)

    op.create_table(
        "item_test_set_items",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("set_id", sa.BigInteger(), nullable=False),
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["set_id"],
            ["item_test_sets.id"],
            name="fk_item_test_set_items_set_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_item_test_set_items_item_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("set_id", "item_id", name="uq_item_test_set_items_set_id_item_id"),
    )
    op.create_index("ix_item_test_set_items_set_id", "item_test_set_items", ["set_id"], unique=False)
    op.create_index("ix_item_test_set_items_item_id", "item_test_set_items", ["item_id"], unique=False)

    op.execute(
        """
        INSERT INTO item_test_sets(code, name)
        VALUES ('DEFAULT', 'Default test item set')
        ON CONFLICT DO NOTHING
        """
    )
