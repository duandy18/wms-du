"""add item test sets

Revision ID: d95f7d97126f
Revises: e6ca87cc2174
Create Date: 2026-02-14 10:13:24.355462

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d95f7d97126f"
down_revision: Union[str, Sequence[str], None] = "e6ca87cc2174"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- item_test_sets ---
    op.create_table(
        "item_test_sets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_item_test_sets_code", "item_test_sets", ["code"], unique=True)

    # --- item_test_set_items ---
    op.create_table(
        "item_test_set_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
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

    # 预置默认集合：code='DEFAULT'
    op.execute(
        sa.text(
            """
            INSERT INTO item_test_sets(code, name)
            VALUES ('DEFAULT', 'Default Test Set')
            ON CONFLICT (code) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_item_test_set_items_item_id", table_name="item_test_set_items")
    op.drop_index("ix_item_test_set_items_set_id", table_name="item_test_set_items")
    op.drop_table("item_test_set_items")

    op.drop_index("ix_item_test_sets_code", table_name="item_test_sets")
    op.drop_table("item_test_sets")
