"""create purchase_order_line_completion

Revision ID: 9beb31ce43a3
Revises: 5028e6e55b24
Create Date: 2026-04-13 17:21:17.935190

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9beb31ce43a3"
down_revision: Union[str, Sequence[str], None] = "5028e6e55b24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "purchase_order_line_completion",
        sa.Column(
            "po_line_id",
            sa.Integer(),
            sa.ForeignKey("purchase_order_lines.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "po_id",
            sa.Integer(),
            sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("po_no", sa.String(length=64), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("purchaser", sa.String(length=64), nullable=False),
        sa.Column("purchase_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_name", sa.String(length=255), nullable=True),
        sa.Column("item_sku", sa.String(length=64), nullable=True),
        sa.Column("spec_text", sa.String(length=255), nullable=True),
        sa.Column("purchase_uom_id_snapshot", sa.Integer(), nullable=False),
        sa.Column("purchase_uom_name_snapshot", sa.String(length=64), nullable=False),
        sa.Column("purchase_ratio_to_base_snapshot", sa.Integer(), nullable=False),
        sa.Column("qty_ordered_input", sa.Integer(), nullable=False),
        sa.Column("qty_ordered_base", sa.Integer(), nullable=False),
        sa.Column(
            "qty_received_base",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("qty_remaining_base", sa.Integer(), nullable=False),
        sa.Column("line_completion_status", sa.String(length=32), nullable=False),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "qty_ordered_input > 0",
            name="ck_polc_qty_ordered_input_positive",
        ),
        sa.CheckConstraint(
            "qty_ordered_base > 0",
            name="ck_polc_qty_ordered_base_positive",
        ),
        sa.CheckConstraint(
            "qty_received_base >= 0",
            name="ck_polc_qty_received_base_nonneg",
        ),
        sa.CheckConstraint(
            "qty_remaining_base >= 0",
            name="ck_polc_qty_remaining_base_nonneg",
        ),
        sa.CheckConstraint(
            "purchase_ratio_to_base_snapshot >= 1",
            name="ck_polc_ratio_positive",
        ),
        sa.CheckConstraint(
            "qty_remaining_base = GREATEST(qty_ordered_base - qty_received_base, 0)",
            name="ck_polc_qty_remaining_consistent",
        ),
        sa.CheckConstraint(
            "line_completion_status IN ('NOT_RECEIVED', 'PARTIAL', 'RECEIVED')",
            name="ck_polc_status",
        ),
        sa.UniqueConstraint("po_id", "line_no", name="uq_polc_po_line_no"),
    )

    op.create_index("ix_polc_po_id", "purchase_order_line_completion", ["po_id"])
    op.create_index("ix_polc_po_no", "purchase_order_line_completion", ["po_no"])
    op.create_index("ix_polc_supplier_id", "purchase_order_line_completion", ["supplier_id"])
    op.create_index("ix_polc_warehouse_id", "purchase_order_line_completion", ["warehouse_id"])
    op.create_index("ix_polc_item_id", "purchase_order_line_completion", ["item_id"])
    op.create_index("ix_polc_item_sku", "purchase_order_line_completion", ["item_sku"])
    op.create_index(
        "ix_polc_completion_status",
        "purchase_order_line_completion",
        ["line_completion_status"],
    )
    op.create_index(
        "ix_polc_purchase_time",
        "purchase_order_line_completion",
        ["purchase_time"],
    )
    op.create_index(
        "ix_polc_last_received_at",
        "purchase_order_line_completion",
        ["last_received_at"],
    )

    op.execute(
        """
        INSERT INTO purchase_order_line_completion (
          po_line_id,
          po_id,
          po_no,
          line_no,
          warehouse_id,
          supplier_id,
          supplier_name,
          purchaser,
          purchase_time,
          item_id,
          item_name,
          item_sku,
          spec_text,
          purchase_uom_id_snapshot,
          purchase_uom_name_snapshot,
          purchase_ratio_to_base_snapshot,
          qty_ordered_input,
          qty_ordered_base,
          qty_received_base,
          qty_remaining_base,
          line_completion_status,
          last_received_at
        )
        WITH completed AS (
          SELECT
            iel.po_line_id AS po_line_id,
            COALESCE(SUM(iel.qty_base), 0)::int AS qty_received_base,
            MAX(we.occurred_at) AS last_received_at
          FROM inbound_event_lines iel
          JOIN wms_events we
            ON we.id = iel.event_id
          WHERE iel.po_line_id IS NOT NULL
            AND we.event_type = 'INBOUND'
            AND we.source_type = 'PURCHASE_ORDER'
            AND we.event_kind = 'COMMIT'
            AND we.status = 'COMMITTED'
          GROUP BY iel.po_line_id
        )
        SELECT
          pol.id AS po_line_id,
          po.id AS po_id,
          po.po_no AS po_no,
          pol.line_no AS line_no,
          po.warehouse_id AS warehouse_id,
          po.supplier_id AS supplier_id,
          po.supplier_name AS supplier_name,
          po.purchaser AS purchaser,
          po.purchase_time AS purchase_time,
          pol.item_id AS item_id,
          pol.item_name AS item_name,
          pol.item_sku AS item_sku,
          pol.spec_text AS spec_text,
          pol.purchase_uom_id_snapshot AS purchase_uom_id_snapshot,
          COALESCE(iu.display_name, iu.uom) AS purchase_uom_name_snapshot,
          pol.purchase_ratio_to_base_snapshot AS purchase_ratio_to_base_snapshot,
          pol.qty_ordered_input AS qty_ordered_input,
          pol.qty_ordered_base AS qty_ordered_base,
          COALESCE(c.qty_received_base, 0)::int AS qty_received_base,
          GREATEST(pol.qty_ordered_base - COALESCE(c.qty_received_base, 0), 0)::int AS qty_remaining_base,
          CASE
            WHEN COALESCE(c.qty_received_base, 0) <= 0 THEN 'NOT_RECEIVED'
            WHEN COALESCE(c.qty_received_base, 0) < pol.qty_ordered_base THEN 'PARTIAL'
            ELSE 'RECEIVED'
          END AS line_completion_status,
          c.last_received_at AS last_received_at
        FROM purchase_order_lines pol
        JOIN purchase_orders po
          ON po.id = pol.po_id
        JOIN item_uoms iu
          ON iu.id = pol.purchase_uom_id_snapshot
        LEFT JOIN completed c
          ON c.po_line_id = pol.id
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_polc_last_received_at", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_purchase_time", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_completion_status", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_item_sku", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_item_id", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_warehouse_id", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_supplier_id", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_po_no", table_name="purchase_order_line_completion")
    op.drop_index("ix_polc_po_id", table_name="purchase_order_line_completion")
    op.drop_table("purchase_order_line_completion")
