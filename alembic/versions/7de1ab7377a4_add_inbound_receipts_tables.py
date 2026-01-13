"""add inbound_receipts tables

Revision ID: 7de1ab7377a4
Revises: b7b55a3a78e1
Create Date: 2026-01-13 11:58:43.989657

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7de1ab7377a4"
down_revision: Union[str, Sequence[str], None] = "b7b55a3a78e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------
    # inbound_receipts（收货主表）
    # ---------------------------
    op.create_table(
        "inbound_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),  # PO / ORDER / OTHER
        sa.Column("source_id", sa.Integer(), nullable=True),  # po_id / order_id / etc.
        sa.Column("receive_task_id", sa.Integer(), nullable=True),  # receive_tasks.id（幂等锚点）
        sa.Column("ref", sa.String(length=128), nullable=False),  # RT-xxx / RMA-xxx
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONFIRMED"),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_inbound_receipts_wh", "inbound_receipts", ["warehouse_id"])
    op.create_index("ix_inbound_receipts_supplier", "inbound_receipts", ["supplier_id"])
    op.create_index("ix_inbound_receipts_ref", "inbound_receipts", ["ref"])
    op.create_index("ix_inbound_receipts_trace", "inbound_receipts", ["trace_id"])
    op.create_index("ix_inbound_receipts_occurred_at", "inbound_receipts", ["occurred_at"])

    # 幂等：一个 receive_task_id 只允许产生一张收货单（NULL 可重复）
    op.create_unique_constraint(
        "uq_inbound_receipts_receive_task_id",
        "inbound_receipts",
        ["receive_task_id"],
    )

    op.create_foreign_key(
        "fk_inbound_receipts_warehouse",
        "inbound_receipts",
        "warehouses",
        ["warehouse_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inbound_receipts_supplier",
        "inbound_receipts",
        "suppliers",
        ["supplier_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_inbound_receipts_receive_task",
        "inbound_receipts",
        "receive_tasks",
        ["receive_task_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -------------------------------
    # inbound_receipt_lines（收货明细）
    # -------------------------------
    op.create_table(
        "inbound_receipt_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("po_line_id", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=True),
        sa.Column("item_sku", sa.String(length=64), nullable=True),
        sa.Column("batch_code", sa.String(length=64), nullable=False),
        sa.Column("production_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("qty_received", sa.Integer(), nullable=False),  # 采购单位数量
        sa.Column("units_per_case", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("qty_units", sa.Integer(), nullable=False),  # 折算最小单位数量
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("line_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("remark", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_inbound_receipt_lines_receipt", "inbound_receipt_lines", ["receipt_id"])
    op.create_index("ix_inbound_receipt_lines_item", "inbound_receipt_lines", ["item_id"])
    op.create_index(
        "ix_inbound_receipt_lines_item_batch",
        "inbound_receipt_lines",
        ["item_id", "batch_code"],
    )

    op.create_unique_constraint(
        "uq_inbound_receipt_lines_receipt_line_no",
        "inbound_receipt_lines",
        ["receipt_id", "line_no"],
    )

    op.create_foreign_key(
        "fk_inbound_receipt_lines_receipt",
        "inbound_receipt_lines",
        "inbound_receipts",
        ["receipt_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_lines_item",
        "inbound_receipt_lines",
        "items",
        ["item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_inbound_receipt_lines_po_line",
        "inbound_receipt_lines",
        "purchase_order_lines",
        ["po_line_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_table("inbound_receipt_lines")
    op.drop_table("inbound_receipts")
