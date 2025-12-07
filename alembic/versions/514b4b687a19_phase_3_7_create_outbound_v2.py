"""phase_3_7_create_outbound_v2

Revision ID: 514b4b687a19
Revises: ea1ea0953f72
Create Date: 2025-11-16 11:24:40.772288
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "514b4b687a19"
down_revision: Union[str, Sequence[str], None] = "ea1ea0953f72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create outbound_commits_v2 + outbound_lines_v2."""
    op.create_table(
        "outbound_commits_v2",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=128), nullable=False),
        sa.Column("ref", sa.String(length=128), nullable=False),
        sa.Column("external_order_ref", sa.String(length=128), nullable=True),
        sa.Column(
            "state",
            sa.String(length=32),
            nullable=False,
            server_default="COMPLETED",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "platform",
            "shop_id",
            "ref",
            name="uq_outbound_commits_v2_platform_shop_ref",
        ),
    )
    op.create_index(
        "ix_outbound_commits_v2_trace_id",
        "outbound_commits_v2",
        ["trace_id"],
        unique=False,
    )

    op.create_table(
        "outbound_lines_v2",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("commit_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("batch_code", sa.String(length=64), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("ledger_ref", sa.String(length=128), nullable=True),
        sa.Column("ledger_trace_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["commit_id"],
            ["outbound_commits_v2.id"],
            name="fk_outbound_lines_v2_commit",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        "ix_outbound_lines_v2_commit",
        "outbound_lines_v2",
        ["commit_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbound_lines_v2_slot",
        "outbound_lines_v2",
        ["warehouse_id", "item_id", "batch_code"],
        unique=False,
    )


def downgrade() -> None:
    """Drop outbound_commits_v2 + outbound_lines_v2."""
    op.drop_index("ix_outbound_lines_v2_slot", table_name="outbound_lines_v2")
    op.drop_index("ix_outbound_lines_v2_commit", table_name="outbound_lines_v2")
    op.drop_table("outbound_lines_v2")

    op.drop_index("ix_outbound_commits_v2_trace_id", table_name="outbound_commits_v2")
    op.drop_table("outbound_commits_v2")
