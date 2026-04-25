"""finance purchase price ledger lines

Revision ID: 3f940aff7149
Revises: c3c25b634e54
Create Date: auto

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3f940aff7149'
down_revision: Union[str, Sequence[str], None] = 'c3c25b634e54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "finance_purchase_price_ledger_lines"


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("po_line_id", sa.Integer(), nullable=False),
        sa.Column("po_id", sa.Integer(), nullable=False),
        sa.Column("po_no", sa.String(length=64), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("item_sku", sa.String(length=64), nullable=True),
        sa.Column("item_name", sa.String(length=255), nullable=True),
        sa.Column("spec_text", sa.String(length=255), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("supplier_name", sa.String(length=255), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_name", sa.String(length=100), nullable=False),
        sa.Column("purchase_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purchase_date", sa.Date(), nullable=False),
        sa.Column("qty_ordered_input", sa.Integer(), nullable=False),
        sa.Column("purchase_uom_name_snapshot", sa.String(length=64), nullable=False),
        sa.Column("purchase_ratio_to_base_snapshot", sa.Integer(), nullable=False),
        sa.Column("qty_ordered_base", sa.Integer(), nullable=False),
        sa.Column("purchase_unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "planned_line_amount",
            sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "po_line_id",
            name="uq_finance_purchase_price_ledger_lines_po_line_id",
        ),
        sa.CheckConstraint("qty_ordered_input > 0", name="ck_fpp_ledger_qty_input_positive"),
        sa.CheckConstraint("qty_ordered_base > 0", name="ck_fpp_ledger_qty_base_positive"),
        sa.CheckConstraint(
            "purchase_ratio_to_base_snapshot >= 1",
            name="ck_fpp_ledger_ratio_positive",
        ),
    )

    op.create_index("ix_fpp_ledger_item_id", TABLE_NAME, ["item_id"])
    op.create_index("ix_fpp_ledger_item_sku", TABLE_NAME, ["item_sku"])
    op.create_index("ix_fpp_ledger_supplier_id", TABLE_NAME, ["supplier_id"])
    op.create_index("ix_fpp_ledger_warehouse_id", TABLE_NAME, ["warehouse_id"])
    op.create_index("ix_fpp_ledger_purchase_date", TABLE_NAME, ["purchase_date"])
    op.create_index("ix_fpp_ledger_item_warehouse", TABLE_NAME, ["item_id", "warehouse_id"])
    op.create_index("ix_fpp_ledger_item_supplier", TABLE_NAME, ["item_id", "supplier_id"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_refresh_purchase_price_ledger_line(p_po_line_id integer)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
          INSERT INTO finance_purchase_price_ledger_lines (
            po_line_id,
            po_id,
            po_no,
            line_no,
            item_id,
            item_sku,
            item_name,
            spec_text,
            supplier_id,
            supplier_name,
            warehouse_id,
            warehouse_name,
            purchase_time,
            purchase_date,
            qty_ordered_input,
            purchase_uom_name_snapshot,
            purchase_ratio_to_base_snapshot,
            qty_ordered_base,
            purchase_unit_price,
            planned_line_amount,
            source_updated_at,
            calculated_at
          )
          SELECT
            pol.id AS po_line_id,
            po.id AS po_id,
            po.po_no AS po_no,
            pol.line_no AS line_no,
            pol.item_id AS item_id,
            pol.item_sku AS item_sku,
            pol.item_name AS item_name,
            pol.spec_text AS spec_text,
            po.supplier_id AS supplier_id,
            COALESCE(po.supplier_name, '') AS supplier_name,
            po.warehouse_id AS warehouse_id,
            COALESCE(wh.name, '') AS warehouse_name,
            po.purchase_time AS purchase_time,
            DATE(po.purchase_time) AS purchase_date,
            pol.qty_ordered_input AS qty_ordered_input,
            pol.purchase_uom_name_snapshot AS purchase_uom_name_snapshot,
            pol.purchase_ratio_to_base_snapshot AS purchase_ratio_to_base_snapshot,
            pol.qty_ordered_base AS qty_ordered_base,
            pol.supply_price AS purchase_unit_price,
            (
              COALESCE(pol.supply_price, 0::numeric(12, 2))
              * COALESCE(pol.qty_ordered_base, 0)
            )::numeric(14, 2) AS planned_line_amount,
            GREATEST(pol.updated_at, po.updated_at) AS source_updated_at,
            now() AS calculated_at
          FROM purchase_order_lines pol
          JOIN purchase_orders po ON po.id = pol.po_id
          JOIN warehouses wh ON wh.id = po.warehouse_id
          WHERE pol.id = p_po_line_id
          ON CONFLICT (po_line_id) DO UPDATE SET
            po_id = EXCLUDED.po_id,
            po_no = EXCLUDED.po_no,
            line_no = EXCLUDED.line_no,
            item_id = EXCLUDED.item_id,
            item_sku = EXCLUDED.item_sku,
            item_name = EXCLUDED.item_name,
            spec_text = EXCLUDED.spec_text,
            supplier_id = EXCLUDED.supplier_id,
            supplier_name = EXCLUDED.supplier_name,
            warehouse_id = EXCLUDED.warehouse_id,
            warehouse_name = EXCLUDED.warehouse_name,
            purchase_time = EXCLUDED.purchase_time,
            purchase_date = EXCLUDED.purchase_date,
            qty_ordered_input = EXCLUDED.qty_ordered_input,
            purchase_uom_name_snapshot = EXCLUDED.purchase_uom_name_snapshot,
            purchase_ratio_to_base_snapshot = EXCLUDED.purchase_ratio_to_base_snapshot,
            qty_ordered_base = EXCLUDED.qty_ordered_base,
            purchase_unit_price = EXCLUDED.purchase_unit_price,
            planned_line_amount = EXCLUDED.planned_line_amount,
            source_updated_at = EXCLUDED.source_updated_at,
            calculated_at = now();
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_purchase_price_ledger_line_upsert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          PERFORM finance_refresh_purchase_price_ledger_line(NEW.id);
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_purchase_price_ledger_line_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          DELETE FROM finance_purchase_price_ledger_lines
          WHERE po_line_id = OLD.id;
          RETURN OLD;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_purchase_price_ledger_po_refresh()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          v_line_id integer;
        BEGIN
          FOR v_line_id IN
            SELECT id FROM purchase_order_lines WHERE po_id = NEW.id
          LOOP
            PERFORM finance_refresh_purchase_price_ledger_line(v_line_id);
          END LOOP;
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_purchase_price_ledger_warehouse_refresh()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          v_line_id integer;
        BEGIN
          FOR v_line_id IN
            SELECT pol.id
            FROM purchase_order_lines pol
            JOIN purchase_orders po ON po.id = pol.po_id
            WHERE po.warehouse_id = NEW.id
          LOOP
            PERFORM finance_refresh_purchase_price_ledger_line(v_line_id);
          END LOOP;
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_fpp_ledger_pol_upsert
        AFTER INSERT OR UPDATE ON purchase_order_lines
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_purchase_price_ledger_line_upsert()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_fpp_ledger_pol_delete
        AFTER DELETE ON purchase_order_lines
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_purchase_price_ledger_line_delete()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_fpp_ledger_po_refresh
        AFTER UPDATE OF po_no, warehouse_id, supplier_id, supplier_name, purchase_time, updated_at
        ON purchase_orders
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_purchase_price_ledger_po_refresh()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_fpp_ledger_warehouse_refresh
        AFTER UPDATE OF name
        ON warehouses
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_purchase_price_ledger_warehouse_refresh()
        """
    )

    op.execute(
        """
        SELECT finance_refresh_purchase_price_ledger_line(pol.id)
        FROM purchase_order_lines pol
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.execute("DROP TRIGGER IF EXISTS trg_fpp_ledger_warehouse_refresh ON warehouses")
    op.execute("DROP TRIGGER IF EXISTS trg_fpp_ledger_po_refresh ON purchase_orders")
    op.execute("DROP TRIGGER IF EXISTS trg_fpp_ledger_pol_delete ON purchase_order_lines")
    op.execute("DROP TRIGGER IF EXISTS trg_fpp_ledger_pol_upsert ON purchase_order_lines")

    op.execute("DROP FUNCTION IF EXISTS finance_trg_purchase_price_ledger_warehouse_refresh()")
    op.execute("DROP FUNCTION IF EXISTS finance_trg_purchase_price_ledger_po_refresh()")
    op.execute("DROP FUNCTION IF EXISTS finance_trg_purchase_price_ledger_line_delete()")
    op.execute("DROP FUNCTION IF EXISTS finance_trg_purchase_price_ledger_line_upsert()")
    op.execute("DROP FUNCTION IF EXISTS finance_refresh_purchase_price_ledger_line(integer)")

    op.drop_index("ix_fpp_ledger_item_supplier", table_name=TABLE_NAME)
    op.drop_index("ix_fpp_ledger_item_warehouse", table_name=TABLE_NAME)
    op.drop_index("ix_fpp_ledger_purchase_date", table_name=TABLE_NAME)
    op.drop_index("ix_fpp_ledger_warehouse_id", table_name=TABLE_NAME)
    op.drop_index("ix_fpp_ledger_supplier_id", table_name=TABLE_NAME)
    op.drop_index("ix_fpp_ledger_item_sku", table_name=TABLE_NAME)
    op.drop_index("ix_fpp_ledger_item_id", table_name=TABLE_NAME)

    op.drop_table(TABLE_NAME)
