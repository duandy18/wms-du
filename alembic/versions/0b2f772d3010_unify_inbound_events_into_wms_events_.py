"""unify inbound events into wms events and add stock_ledger event_id

Revision ID: 0b2f772d3010
Revises: 31d1f02ceefe
Create Date: 2026-04-12 22:34:17.517409

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0b2f772d3010"
down_revision: Union[str, Sequence[str], None] = "31d1f02ceefe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = :t
                LIMIT 1
                """
            ),
            {"t": table_name},
        ).scalar()
    )


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = :t
                  AND column_name = :c
                LIMIT 1
                """
            ),
            {"t": table_name, "c": column_name},
        ).scalar()
    )


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = (:t)::regclass
                  AND conname = :c
                LIMIT 1
                """
            ),
            {"t": f"public.{table_name}", "c": constraint_name},
        ).scalar()
    )


def _index_exists(conn, index_name: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                """
                SELECT 1
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'i'
                  AND n.nspname = 'public'
                  AND c.relname = :i
                LIMIT 1
                """
            ),
            {"i": index_name},
        ).scalar()
    )


def _rename_constraint_if_exists(conn, table_name: str, old: str, new: str) -> None:
    if _constraint_exists(conn, table_name, old) and not _constraint_exists(conn, table_name, new):
        op.execute(f"ALTER TABLE {table_name} RENAME CONSTRAINT {old} TO {new}")


def _rename_index_if_exists(conn, old: str, new: str) -> None:
    if _index_exists(conn, old) and not _index_exists(conn, new):
        op.execute(f"ALTER INDEX {old} RENAME TO {new}")


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()

    has_inbound_events = _table_exists(conn, "inbound_events")
    has_wms_events = _table_exists(conn, "wms_events")

    # ------------------------------------------------------------
    # 1) 兼容两种前态：
    #    A. 老前态：31d1f02ceefe 创建 inbound_events
    #    B. 新前态：31d1f02ceefe 已直接创建 wms_events
    # ------------------------------------------------------------
    if has_inbound_events and not has_wms_events:
        op.rename_table("inbound_events", "wms_events")

    if _table_exists(conn, "wms_events"):
        # 约束名统一
        _rename_constraint_if_exists(conn, "wms_events", "pk_inbound_events", "pk_wms_events")
        _rename_constraint_if_exists(conn, "wms_events", "uq_inbound_events_event_no", "uq_wms_events_event_no")
        _rename_constraint_if_exists(conn, "wms_events", "uq_inbound_events_trace_id", "uq_wms_events_trace_id")
        _rename_constraint_if_exists(conn, "wms_events", "ck_inbound_events_source_type", "ck_wms_events_source_type")
        _rename_constraint_if_exists(conn, "wms_events", "ck_inbound_events_event_kind", "ck_wms_events_event_kind")
        _rename_constraint_if_exists(conn, "wms_events", "ck_inbound_events_status", "ck_wms_events_status")
        _rename_constraint_if_exists(conn, "wms_events", "fk_inbound_events_warehouse", "fk_wms_events_warehouse")
        _rename_constraint_if_exists(conn, "wms_events", "fk_inbound_events_target_event", "fk_wms_events_target_event")
        _rename_constraint_if_exists(conn, "wms_events", "fk_inbound_events_created_by", "fk_wms_events_created_by")

        # 索引名统一
        _rename_index_if_exists(conn, "ix_inbound_events_warehouse_occurred_at", "ix_wms_events_warehouse_occurred_at")
        _rename_index_if_exists(conn, "ix_inbound_events_source_type", "ix_wms_events_source_type")
        _rename_index_if_exists(conn, "ix_inbound_events_target_event_id", "ix_wms_events_target_event_id")

    # ------------------------------------------------------------
    # 2) wms_events 增加 event_type，并把历史行回填为 INBOUND
    # ------------------------------------------------------------
    if _table_exists(conn, "wms_events") and not _column_exists(conn, "wms_events", "event_type"):
        op.add_column(
            "wms_events",
            sa.Column(
                "event_type",
                sa.String(length=16),
                nullable=True,
                server_default=sa.text("'INBOUND'"),
            ),
        )

    if _table_exists(conn, "wms_events"):
        op.execute("UPDATE wms_events SET event_type = 'INBOUND' WHERE event_type IS NULL")

        op.alter_column(
            "wms_events",
            "event_type",
            existing_type=sa.String(length=16),
            nullable=False,
            server_default=None,
        )

        if not _constraint_exists(conn, "wms_events", "ck_wms_events_event_type"):
            op.create_check_constraint(
                "ck_wms_events_event_type",
                "wms_events",
                "event_type IN ('INBOUND', 'OUTBOUND', 'COUNT')",
            )

        if not _index_exists(conn, "ix_wms_events_event_type"):
            op.create_index(
                "ix_wms_events_event_type",
                "wms_events",
                ["event_type"],
                unique=False,
            )

    # ------------------------------------------------------------
    # 3) stock_ledger 增加正式 event_id
    # ------------------------------------------------------------
    if not _column_exists(conn, "stock_ledger", "event_id"):
        op.add_column("stock_ledger", sa.Column("event_id", sa.Integer(), nullable=True))

    if not _index_exists(conn, "ix_stock_ledger_event_id"):
        op.create_index(
            "ix_stock_ledger_event_id",
            "stock_ledger",
            ["event_id"],
            unique=False,
        )

    if not _constraint_exists(conn, "stock_ledger", "fk_stock_ledger_event"):
        op.create_foreign_key(
            "fk_stock_ledger_event",
            "stock_ledger",
            "wms_events",
            ["event_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Downgrade."""
    conn = op.get_bind()

    # 1) 回滚 stock_ledger.event_id
    if _constraint_exists(conn, "stock_ledger", "fk_stock_ledger_event"):
        op.drop_constraint("fk_stock_ledger_event", "stock_ledger", type_="foreignkey")

    if _index_exists(conn, "ix_stock_ledger_event_id"):
        op.drop_index("ix_stock_ledger_event_id", table_name="stock_ledger")

    if _column_exists(conn, "stock_ledger", "event_id"):
        op.drop_column("stock_ledger", "event_id")

    # 2) 回滚 wms_events.event_type
    if _index_exists(conn, "ix_wms_events_event_type"):
        op.drop_index("ix_wms_events_event_type", table_name="wms_events")

    if _constraint_exists(conn, "wms_events", "ck_wms_events_event_type"):
        op.drop_constraint("ck_wms_events_event_type", "wms_events", type_="check")

    if _table_exists(conn, "wms_events") and _column_exists(conn, "wms_events", "event_type"):
        op.drop_column("wms_events", "event_type")

    # 3) wms_events -> inbound_events
    if _table_exists(conn, "wms_events") and not _table_exists(conn, "inbound_events"):
        _rename_index_if_exists(conn, "ix_wms_events_target_event_id", "ix_inbound_events_target_event_id")
        _rename_index_if_exists(conn, "ix_wms_events_source_type", "ix_inbound_events_source_type")
        _rename_index_if_exists(conn, "ix_wms_events_warehouse_occurred_at", "ix_inbound_events_warehouse_occurred_at")

        _rename_constraint_if_exists(conn, "wms_events", "fk_wms_events_created_by", "fk_inbound_events_created_by")
        _rename_constraint_if_exists(conn, "wms_events", "fk_wms_events_target_event", "fk_inbound_events_target_event")
        _rename_constraint_if_exists(conn, "wms_events", "fk_wms_events_warehouse", "fk_inbound_events_warehouse")
        _rename_constraint_if_exists(conn, "wms_events", "ck_wms_events_status", "ck_inbound_events_status")
        _rename_constraint_if_exists(conn, "wms_events", "ck_wms_events_event_kind", "ck_inbound_events_event_kind")
        _rename_constraint_if_exists(conn, "wms_events", "ck_wms_events_source_type", "ck_inbound_events_source_type")
        _rename_constraint_if_exists(conn, "wms_events", "uq_wms_events_trace_id", "uq_inbound_events_trace_id")
        _rename_constraint_if_exists(conn, "wms_events", "uq_wms_events_event_no", "uq_inbound_events_event_no")
        _rename_constraint_if_exists(conn, "wms_events", "pk_wms_events", "pk_inbound_events")

        op.rename_table("wms_events", "inbound_events")
