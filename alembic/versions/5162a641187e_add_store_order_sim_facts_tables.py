"""add store order sim facts tables

Revision ID: 5162a641187e
Revises: 8fb963d25b29
Create Date: 2026-02-12 16:21:01.107365
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5162a641187e"
down_revision: Union[str, Sequence[str], None] = "8fb963d25b29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------
    # store_order_sim_merchant_lines
    # -----------------------------
    op.create_table(
        "store_order_sim_merchant_lines",
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column("filled_code", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("spec", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "store_id",
            "row_no",
            name="pk_store_order_sim_merchant_lines",
        ),
    )

    op.create_index(
        "ix_store_order_sim_merchant_lines_store",
        "store_order_sim_merchant_lines",
        ["store_id"],
    )

    # -----------------------------
    # store_order_sim_cart
    # -----------------------------
    op.create_table(
        "store_order_sim_cart",
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("row_no", sa.Integer(), nullable=False),
        sa.Column(
            "checked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("province", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint(
            "store_id",
            "row_no",
            name="pk_store_order_sim_cart",
        ),
    )

    op.create_index(
        "ix_store_order_sim_cart_store",
        "store_order_sim_cart",
        ["store_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_store_order_sim_cart_store", table_name="store_order_sim_cart")
    op.drop_index(
        "ix_store_order_sim_merchant_lines_store",
        table_name="store_order_sim_merchant_lines",
    )
    op.drop_table("store_order_sim_cart")
    op.drop_table("store_order_sim_merchant_lines")
