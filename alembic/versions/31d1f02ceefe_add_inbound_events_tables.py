"""add inbound events tables

Revision ID: 31d1f02ceefe
Revises: e2e22af73937
Create Date: 2026-04-12 21:57:19.385870

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "31d1f02ceefe"
down_revision: Union[str, Sequence[str], None] = "e2e22af73937"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "wms_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_no", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column(
            "event_kind",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'COMMIT'"),
        ),
        sa.Column("target_event_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'COMMITTED'"),
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("remark", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wms_events")),
        sa.UniqueConstraint("event_no", name="uq_wms_events_event_no"),
        sa.UniqueConstraint("trace_id", name="uq_wms_events_trace_id"),
        sa.CheckConstraint(
            "event_type IN ('INBOUND', 'OUTBOUND', 'COUNT')",
            name="ck_wms_events_event_type",
        ),
        sa.CheckConstraint(
            (
                "source_type IN ("
                "'PURCHASE_ORDER', 'MANUAL', 'RETURN', 'TRANSFER_IN', 'ADJUST_IN', "
                "'ORDER_SHIP', 'INTERNAL_OUTBOUND', 'TRANSFER_OUT', 'SCRAP', 'ADJUST_OUT', "
                "'COUNT_TASK', 'MANUAL_COUNT'"
                ")"
            ),
            name="ck_wms_events_source_type",
        ),
        sa.CheckConstraint(
            "event_kind IN ('COMMIT', 'REVERSAL', 'CORRECTION')",
            name="ck_wms_events_event_kind",
        ),
        sa.CheckConstraint(
            "status IN ('COMMITTED', 'VOIDED', 'SUPERSEDED')",
            name="ck_wms_events_status",
        ),
        sa.ForeignKeyConstraint(
            ["warehouse_id"],
            ["warehouses.id"],
            name="fk_wms_events_warehouse",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_event_id"],
            ["wms_events.id"],
            name="fk_wms_events_target_event",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_wms_events_created_by",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_wms_events_warehouse_occurred_at",
        "wms_events",
        ["warehouse_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_wms_events_event_type",
        "wms_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_wms_events_source_type",
        "wms_events",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        "ix_wms_events_target_event_id",
        "wms_events",
        ["target_event_id"],
        unique=False,
    )

    op.create_table(
        "inbound_event_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("uom_id", sa.Integer(), nullable=False),
        sa.Column("barcode_input", sa.String(length=128), nullable=True),
        sa.Column("qty_input", sa.Integer(), nullable=False),
        sa.Column("ratio_to_base_snapshot", sa.Integer(), nullable=False),
        sa.Column("qty_base", sa.Integer(), nullable=False),
        sa.Column("lot_code_input", sa.String(length=128), nullable=True),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("lot_id", sa.Integer(), nullable=True),
        sa.Column("po_line_id", sa.Integer(), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbound_event_lines")),
        sa.UniqueConstraint(
            "event_id",
            "line_no",
            name="uq_inbound_event_lines_event_line",
        ),
        sa.CheckConstraint(
            "(production_date IS NULL) OR (expiry_date IS NULL) OR (production_date <= expiry_date)",
            name="ck_inbound_event_lines_prod_le_exp",
        ),
        sa.CheckConstraint(
            "ratio_to_base_snapshot >= 1",
            name="ck_inbound_event_lines_ratio_positive",
        ),
        sa.CheckConstraint(
            "qty_input >= 1",
            name="ck_inbound_event_lines_qty_input_positive",
        ),
        sa.CheckConstraint(
            "qty_base = (qty_input * ratio_to_base_snapshot)",
            name="ck_inbound_event_lines_qty_base_consistent",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["wms_events.id"],
            name="fk_inbound_event_lines_event",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name="fk_inbound_event_lines_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uom_id"],
            ["item_uoms.id"],
            name="fk_inbound_event_lines_uom",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"],
            ["lots.id"],
            name="fk_inbound_event_lines_lot",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["po_line_id"],
            ["purchase_order_lines.id"],
            name="fk_inbound_event_lines_po_line",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_inbound_event_lines_event_id",
        "inbound_event_lines",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_event_lines_item_id",
        "inbound_event_lines",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_event_lines_lot_id",
        "inbound_event_lines",
        ["lot_id"],
        unique=False,
    )
    op.create_index(
        "ix_inbound_event_lines_po_line_id",
        "inbound_event_lines",
        ["po_line_id"],
        unique=False,
    )

    op.add_column("stock_ledger", sa.Column("event_id", sa.Integer(), nullable=True))
    op.create_index("ix_stock_ledger_event_id", "stock_ledger", ["event_id"], unique=False)
    op.create_foreign_key(
        "fk_stock_ledger_event",
        "stock_ledger",
        "wms_events",
        ["event_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint("fk_stock_ledger_event", "stock_ledger", type_="foreignkey")
    op.drop_index("ix_stock_ledger_event_id", table_name="stock_ledger")
    op.drop_column("stock_ledger", "event_id")

    op.drop_index("ix_inbound_event_lines_po_line_id", table_name="inbound_event_lines")
    op.drop_index("ix_inbound_event_lines_lot_id", table_name="inbound_event_lines")
    op.drop_index("ix_inbound_event_lines_item_id", table_name="inbound_event_lines")
    op.drop_index("ix_inbound_event_lines_event_id", table_name="inbound_event_lines")
    op.drop_table("inbound_event_lines")

    op.drop_index("ix_wms_events_target_event_id", table_name="wms_events")
    op.drop_index("ix_wms_events_source_type", table_name="wms_events")
    op.drop_index("ix_wms_events_event_type", table_name="wms_events")
    op.drop_index("ix_wms_events_warehouse_occurred_at", table_name="wms_events")
    op.drop_table("wms_events")
