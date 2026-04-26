"""finance_order_sales_single_line_amount_fallback

Revision ID: c3a7f8e49b20
Revises: f0acefab2386
Create Date: 2026-04-27

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "c3a7f8e49b20"
down_revision: Union[str, Sequence[str], None] = "f0acefab2386"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_FUNCTION = """
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
  WITH base AS (
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
      oi.amount AS amount_raw,
      oi.line_amount AS line_amount_raw,
      COALESCE(o.pay_amount, o.order_amount, 0) AS order_value,
      (
        SELECT COUNT(*)
          FROM order_items oi2
         WHERE oi2.order_id = o.id
      ) AS order_item_count,
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
  ),
  src AS (
    SELECT
      *,
      CASE
        WHEN amount_raw IS NOT NULL AND amount_raw > 0 THEN amount_raw
        WHEN line_amount_raw IS NOT NULL AND line_amount_raw > 0 THEN line_amount_raw
        WHEN COALESCE(qty_sold, 0) * COALESCE(price, unit_price_raw, 0) > 0
          THEN COALESCE(qty_sold, 0) * COALESCE(price, unit_price_raw, 0)
        WHEN order_item_count = 1 AND order_value > 0 THEN order_value
        ELSE 0
      END AS computed_line_amount
      FROM base
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
      WHEN qty_sold > 0 THEN computed_line_amount / qty_sold
      ELSE NULL
    END AS unit_price,
    discount_amount,
    computed_line_amount AS line_amount,
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


OLD_FUNCTION = """
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


def upgrade() -> None:
    op.execute(NEW_FUNCTION)
    op.execute(
        """
        SELECT finance_refresh_order_sales_line(oi.id)
          FROM order_items oi
        """
    )


def downgrade() -> None:
    op.execute(OLD_FUNCTION)
    op.execute(
        """
        SELECT finance_refresh_order_sales_line(oi.id)
          FROM order_items oi
        """
    )
