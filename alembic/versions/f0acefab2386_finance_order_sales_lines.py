"""finance_order_sales_lines

Revision ID: f0acefab2386
Revises: 28e74f19a54f
Create Date: 2026-04-27 01:15:56.857980

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f0acefab2386"
down_revision: Union[str, Sequence[str], None] = "28e74f19a54f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "finance_order_sales_lines"


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        TABLE_NAME,
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("order_item_id", sa.BigInteger(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column("store_code", sa.String(length=64), nullable=False),
        sa.Column("store_name", sa.String(length=256), nullable=True),
        sa.Column("ext_order_no", sa.String(length=128), nullable=False),
        sa.Column("order_ref", sa.String(length=256), nullable=False),
        sa.Column("order_status", sa.String(length=32), nullable=True),
        sa.Column("order_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("receiver_province", sa.String(length=64), nullable=True),
        sa.Column("receiver_city", sa.String(length=64), nullable=True),
        sa.Column("receiver_district", sa.String(length=64), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=False),
        sa.Column("sku_id", sa.String(length=128), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("qty_sold", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("line_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("order_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("pay_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("qty_sold >= 0", name="ck_fosl_qty_sold_nonneg"),
        sa.CheckConstraint("line_amount >= 0", name="ck_fosl_line_amount_nonneg"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_item_id", name="uq_finance_order_sales_lines_order_item_id"),
    )

    op.create_index("ix_fosl_order_id", TABLE_NAME, ["order_id"])
    op.create_index("ix_fosl_order_item_id", TABLE_NAME, ["order_item_id"])
    op.create_index("ix_fosl_platform_store", TABLE_NAME, ["platform", "store_code"])
    op.create_index("ix_fosl_store_id", TABLE_NAME, ["store_id"])
    op.create_index("ix_fosl_store_code", TABLE_NAME, ["store_code"])
    op.create_index("ix_fosl_order_ref", TABLE_NAME, ["order_ref"])
    op.create_index("ix_fosl_ext_order_no", TABLE_NAME, ["ext_order_no"])
    op.create_index("ix_fosl_order_date", TABLE_NAME, ["order_date"])
    op.create_index("ix_fosl_item_id", TABLE_NAME, ["item_id"])
    op.create_index("ix_fosl_sku_id", TABLE_NAME, ["sku_id"])

    op.execute(
        "COMMENT ON COLUMN orders.store_code IS '店铺 ID（字符串，与 stores.store_code 对齐）'"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_refresh_order_sales_line(p_order_item_id bigint)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
          INSERT INTO finance_order_sales_lines (
            order_id,
            order_item_id,
            platform,
            store_id,
            store_code,
            store_name,
            ext_order_no,
            order_ref,
            order_status,
            order_created_at,
            order_date,
            receiver_province,
            receiver_city,
            receiver_district,
            item_id,
            sku_id,
            title,
            qty_sold,
            unit_price,
            discount_amount,
            line_amount,
            order_amount,
            pay_amount,
            source_updated_at,
            calculated_at
          )
          WITH src AS (
            SELECT
              o.id AS order_id,
              oi.id AS order_item_id,
              o.platform AS platform,
              o.store_id AS store_id,
              o.store_code AS store_code,
              s.store_name AS store_name,
              o.ext_order_no AS ext_order_no,
              ('ORD:' || o.platform || ':' || o.store_code || ':' || o.ext_order_no) AS order_ref,
              o.status AS order_status,
              o.created_at AS order_created_at,
              DATE(o.created_at) AS order_date,
              oa.province AS receiver_province,
              oa.city AS receiver_city,
              oa.district AS receiver_district,
              oi.item_id AS item_id,
              oi.sku_id AS sku_id,
              oi.title AS title,
              COALESCE(oi.qty, 0) AS qty_sold,
              oi.price AS price,
              oi.unit_price AS unit_price_raw,
              COALESCE(oi.discount, 0) AS discount_amount,
              CASE
                WHEN oi.amount IS NOT NULL AND oi.amount > 0 THEN oi.amount
                WHEN oi.line_amount IS NOT NULL AND oi.line_amount > 0 THEN oi.line_amount
                ELSE COALESCE(oi.qty, 0) * COALESCE(oi.price, oi.unit_price, 0)
              END AS line_amount,
              o.order_amount AS order_amount,
              o.pay_amount AS pay_amount,
              GREATEST(
                COALESCE(o.updated_at, o.created_at),
                COALESCE(oa.created_at, o.created_at)
              ) AS source_updated_at
              FROM order_items oi
              JOIN orders o
                ON o.id = oi.order_id
              LEFT JOIN stores s
                ON s.id = o.store_id
              LEFT JOIN order_address oa
                ON oa.order_id = o.id
             WHERE oi.id = p_order_item_id
          )
          SELECT
            order_id,
            order_item_id,
            platform,
            store_id,
            store_code,
            store_name,
            ext_order_no,
            order_ref,
            order_status,
            order_created_at,
            order_date,
            receiver_province,
            receiver_city,
            receiver_district,
            item_id,
            sku_id,
            title,
            qty_sold,
            CASE
              WHEN price IS NOT NULL AND price > 0 THEN price
              WHEN unit_price_raw IS NOT NULL AND unit_price_raw > 0 THEN unit_price_raw
              WHEN qty_sold > 0 THEN line_amount / qty_sold
              ELSE NULL
            END AS unit_price,
            discount_amount,
            line_amount,
            order_amount,
            pay_amount,
            source_updated_at,
            now()
            FROM src
          ON CONFLICT (order_item_id)
          DO UPDATE SET
            order_id = EXCLUDED.order_id,
            platform = EXCLUDED.platform,
            store_id = EXCLUDED.store_id,
            store_code = EXCLUDED.store_code,
            store_name = EXCLUDED.store_name,
            ext_order_no = EXCLUDED.ext_order_no,
            order_ref = EXCLUDED.order_ref,
            order_status = EXCLUDED.order_status,
            order_created_at = EXCLUDED.order_created_at,
            order_date = EXCLUDED.order_date,
            receiver_province = EXCLUDED.receiver_province,
            receiver_city = EXCLUDED.receiver_city,
            receiver_district = EXCLUDED.receiver_district,
            item_id = EXCLUDED.item_id,
            sku_id = EXCLUDED.sku_id,
            title = EXCLUDED.title,
            qty_sold = EXCLUDED.qty_sold,
            unit_price = EXCLUDED.unit_price,
            discount_amount = EXCLUDED.discount_amount,
            line_amount = EXCLUDED.line_amount,
            order_amount = EXCLUDED.order_amount,
            pay_amount = EXCLUDED.pay_amount,
            source_updated_at = EXCLUDED.source_updated_at,
            calculated_at = now();
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_refresh_order_sales_lines_for_order(p_order_id bigint)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        DECLARE
          v_order_item_id bigint;
        BEGIN
          FOR v_order_item_id IN
            SELECT oi.id
              FROM order_items oi
             WHERE oi.order_id = p_order_id
          LOOP
            PERFORM finance_refresh_order_sales_line(v_order_item_id);
          END LOOP;

          DELETE FROM finance_order_sales_lines f
           WHERE f.order_id = p_order_id
             AND NOT EXISTS (
               SELECT 1
                 FROM order_items oi
                WHERE oi.id = f.order_item_id
             );
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_order_sales_line_upsert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          PERFORM finance_refresh_order_sales_line(NEW.id);
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_order_sales_line_delete()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          DELETE FROM finance_order_sales_lines
           WHERE order_item_id = OLD.id;
          RETURN OLD;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_order_sales_order_refresh()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            DELETE FROM finance_order_sales_lines
             WHERE order_id = OLD.id;
            RETURN OLD;
          END IF;

          PERFORM finance_refresh_order_sales_lines_for_order(NEW.id);
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_order_sales_address_refresh()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            PERFORM finance_refresh_order_sales_lines_for_order(OLD.order_id);
            RETURN OLD;
          END IF;

          PERFORM finance_refresh_order_sales_lines_for_order(NEW.order_id);
          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION finance_trg_order_sales_store_refresh()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
          v_order_id bigint;
        BEGIN
          FOR v_order_id IN
            SELECT o.id
              FROM orders o
             WHERE o.store_id = NEW.id
          LOOP
            PERFORM finance_refresh_order_sales_lines_for_order(v_order_id);
          END LOOP;

          RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_finance_order_sales_line_upsert
        AFTER INSERT OR UPDATE ON order_items
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_order_sales_line_upsert()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_finance_order_sales_line_delete
        AFTER DELETE ON order_items
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_order_sales_line_delete()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_finance_order_sales_order_refresh
        AFTER UPDATE OF platform, store_id, store_code, ext_order_no, status, order_amount, pay_amount, created_at, updated_at ON orders
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_order_sales_order_refresh()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_finance_order_sales_order_delete
        AFTER DELETE ON orders
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_order_sales_order_refresh()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_finance_order_sales_address_refresh
        AFTER INSERT OR UPDATE OR DELETE ON order_address
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_order_sales_address_refresh()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_finance_order_sales_store_refresh
        AFTER UPDATE OF store_name, platform, store_code ON stores
        FOR EACH ROW
        EXECUTE FUNCTION finance_trg_order_sales_store_refresh()
        """
    )

    op.execute(
        """
        SELECT finance_refresh_order_sales_line(oi.id)
          FROM order_items oi
        """
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.execute("DROP TRIGGER IF EXISTS trg_finance_order_sales_store_refresh ON stores")
    op.execute("DROP TRIGGER IF EXISTS trg_finance_order_sales_address_refresh ON order_address")
    op.execute("DROP TRIGGER IF EXISTS trg_finance_order_sales_order_delete ON orders")
    op.execute("DROP TRIGGER IF EXISTS trg_finance_order_sales_order_refresh ON orders")
    op.execute("DROP TRIGGER IF EXISTS trg_finance_order_sales_line_delete ON order_items")
    op.execute("DROP TRIGGER IF EXISTS trg_finance_order_sales_line_upsert ON order_items")

    op.execute("DROP FUNCTION IF EXISTS finance_trg_order_sales_store_refresh()")
    op.execute("DROP FUNCTION IF EXISTS finance_trg_order_sales_address_refresh()")
    op.execute("DROP FUNCTION IF EXISTS finance_trg_order_sales_order_refresh()")
    op.execute("DROP FUNCTION IF EXISTS finance_trg_order_sales_line_delete()")
    op.execute("DROP FUNCTION IF EXISTS finance_trg_order_sales_line_upsert()")
    op.execute("DROP FUNCTION IF EXISTS finance_refresh_order_sales_lines_for_order(bigint)")
    op.execute("DROP FUNCTION IF EXISTS finance_refresh_order_sales_line(bigint)")

    op.drop_table(TABLE_NAME)
