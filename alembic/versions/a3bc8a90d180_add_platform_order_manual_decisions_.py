"""add platform_order_manual_decisions facts table

Revision ID: a3bc8a90d180
Revises: a0a0e1e9ad09
Create Date: 2026-02-09 17:15:01.516095
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a3bc8a90d180"
down_revision: Union[str, Sequence[str], None] = "a0a0e1e9ad09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_order_manual_decisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),

        # ---- batch / grouping ----
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="one confirm-and-create batch"
        ),

        # ---- order anchor (platform fact) ----
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("ext_order_no", sa.Text(), nullable=False),
        sa.Column(
            "order_id",
            sa.BigInteger(),
            nullable=True,
            comment="internal order id after confirm-and-create"
        ),

        # ---- platform line anchor ----
        sa.Column("line_key", sa.Text(), nullable=True),
        sa.Column("line_no", sa.Integer(), nullable=True),
        sa.Column("platform_sku_id", sa.Text(), nullable=True),
        sa.Column("fact_qty", sa.Integer(), nullable=True),

        # ---- manual decision ----
        sa.Column("item_id", sa.BigInteger(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),

        # ---- governance context ----
        sa.Column(
            "manual_reason",
            sa.Text(),
            nullable=True,
            comment="e.g. MISSING_PSKU / NO_BINDING / TITLE_AMBIGUOUS"
        ),
        sa.Column(
            "risk_flags",
            postgresql.JSONB(),
            nullable=True,
            comment="risk flags at decision time"
        ),

        # ---- time ----
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ---- indexes for read paths ----
    op.create_index(
        "idx_pomd_order_anchor",
        "platform_order_manual_decisions",
        ["platform", "store_id", "ext_order_no", "created_at"],
    )

    op.create_index(
        "idx_pomd_created_at",
        "platform_order_manual_decisions",
        ["created_at"],
    )

    op.create_index(
        "idx_pomd_store_created",
        "platform_order_manual_decisions",
        ["store_id", "created_at"],
    )

    op.create_index(
        "idx_pomd_order_id",
        "platform_order_manual_decisions",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_pomd_order_id", table_name="platform_order_manual_decisions")
    op.drop_index("idx_pomd_store_created", table_name="platform_order_manual_decisions")
    op.drop_index("idx_pomd_created_at", table_name="platform_order_manual_decisions")
    op.drop_index("idx_pomd_order_anchor", table_name="platform_order_manual_decisions")
    op.drop_table("platform_order_manual_decisions")
