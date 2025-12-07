"""add_event_store_and_ledger_uq

Revision ID: 3bd0c5797f13
Revises: 6b578e4ca158
Create Date: 2025-12-07 17:48:46.373835

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision: str = "3bd0c5797f13"
down_revision: Union[str, Sequence[str], None] = "6b578e4ca158"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add event_store table (if missing) and ledger UQ for idempotency."""
    conn = op.get_bind()

    # ---------- Helpers ----------
    def table_exists(name: str) -> bool:
        return (
            conn.execute(
                text(
                    """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :t
                """
                ),
                {"t": name},
            ).scalar()
            is not None
        )

    def constraint_exists(table: str, name: str) -> bool:
        return (
            conn.execute(
                text(
                    """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = :t
                  AND constraint_name = :n
                """
                ),
                {"t": table, "n": name},
            ).scalar()
            is not None
        )

    def index_exists(table: str, name: str) -> bool:
        return (
            conn.execute(
                text(
                    """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = :t
                  AND indexname = :n
                """
                ),
                {"t": table, "n": name},
            ).scalar()
            is not None
        )

    # ==========================================
    # 1) event_store 补表（若不存在）
    # ==========================================
    if not table_exists("event_store"):
        op.create_table(
            "event_store",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("trace_id", sa.String(length=255), nullable=False),
            sa.Column("topic", sa.String(length=255), nullable=True),
            sa.Column("key", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=True),
            sa.Column("payload", pg.JSONB, nullable=True),
            sa.Column("headers", pg.JSONB, nullable=True),
        )

    if not index_exists("event_store", "ix_event_store_trace_ts"):
        op.create_index(
            "ix_event_store_trace_ts",
            "event_store",
            ["trace_id", "occurred_at", "id"],
        )

    # ==========================================
    # 2) stock_ledger 补幂等唯一约束
    #    uq_ledger_wh_batch_item_reason_ref_line
    # ==========================================
    if not constraint_exists("stock_ledger", "uq_ledger_wh_batch_item_reason_ref_line"):
        op.create_unique_constraint(
            "uq_ledger_wh_batch_item_reason_ref_line",
            "stock_ledger",
            ["warehouse_id", "batch_code", "item_id", "reason", "ref", "ref_line"],
        )


def downgrade() -> None:
    """Best-effort rollback: drop UQ and event_store (if present)."""
    conn = op.get_bind()

    def table_exists(name: str) -> bool:
        return (
            conn.execute(
                text(
                    """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :t
                """
                ),
                {"t": name},
            ).scalar()
            is not None
        )

    def constraint_exists(table: str, name: str) -> bool:
        return (
            conn.execute(
                text(
                    """
                SELECT 1
                FROM information_schema.table_constraints
                WHERE table_schema = 'public'
                  AND table_name = :t
                  AND constraint_name = :n
                """
                ),
                {"t": table, "n": name},
            ).scalar()
            is not None
        )

    def index_exists(table: str, name: str) -> bool:
        return (
            conn.execute(
                text(
                    """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename = :t
                  AND indexname = :n
                """
                ),
                {"t": table, "n": name},
            ).scalar()
            is not None
        )

    # 1) 回滚 stock_ledger 上的 UQ
    if constraint_exists("stock_ledger", "uq_ledger_wh_batch_item_reason_ref_line"):
        op.drop_constraint(
            "uq_ledger_wh_batch_item_reason_ref_line",
            "stock_ledger",
            type_="unique",
        )

    # 2) 回滚 event_store（先索引后表）
    if index_exists("event_store", "ix_event_store_trace_ts"):
        op.drop_index("ix_event_store_trace_ts", table_name="event_store")

    if table_exists("event_store"):
        op.drop_table("event_store")
