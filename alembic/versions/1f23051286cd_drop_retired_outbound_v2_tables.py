"""drop retired outbound v2 tables

Revision ID: 1f23051286cd
Revises: 36ee63805894
Create Date: 2026-04-25 15:46:08.734600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f23051286cd'
down_revision: Union[str, Sequence[str], None] = '36ee63805894'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop retired legacy outbound v2 tables.

    Runtime write path and read path have moved to:
    - formal WMS outbound submit services
    - order_fulfillment.shipped_at for SLA metrics
    - stock_ledger / outbound_event_lines for inventory facts

    Historical migration files are intentionally left unchanged.
    """
    op.drop_index("ix_outbound_lines_v2_slot", table_name="outbound_lines_v2")
    op.drop_index("ix_outbound_lines_v2_commit", table_name="outbound_lines_v2")
    op.drop_table("outbound_lines_v2")

    op.drop_index("ix_outbound_commits_v2_trace_id", table_name="outbound_commits_v2")
    op.drop_table("outbound_commits_v2")


def downgrade() -> None:
    """Recreate retired outbound v2 tables for rollback only."""
    op.create_table(
        "outbound_commits_v2",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("shop_id", sa.String(length=128), nullable=False),
        sa.Column("ref", sa.String(length=128), nullable=False),
        sa.Column("external_order_ref", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="COMPLETED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("platform", "shop_id", "ref", name="uq_outbound_commits_v2_platform_shop_ref"),
    )
    op.create_index("ix_outbound_commits_v2_trace_id", "outbound_commits_v2", ["trace_id"])

    op.create_table(
        "outbound_lines_v2",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("commit_id", sa.BigInteger(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("batch_code", sa.String(length=64), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("ledger_ref", sa.String(length=128), nullable=True),
        sa.Column("ledger_trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["commit_id"],
            ["outbound_commits_v2.id"],
            name="fk_outbound_lines_v2_commit",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index("ix_outbound_lines_v2_commit", "outbound_lines_v2", ["commit_id"])
    op.create_index("ix_outbound_lines_v2_slot", "outbound_lines_v2", ["warehouse_id", "item_id", "batch_code"])
