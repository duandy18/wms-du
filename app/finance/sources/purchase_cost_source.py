from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.services.common import ratio, to_decimal


class PurchaseCostSource:
    """
    采购成本只读来源。

    边界：
    - 只读 procurement 采购计划事实：purchase_orders / purchase_order_lines
    - supply_price 是已折扣后的实际基础单位采购价
    - 采购金额 = supply_price * qty_ordered_base
    - 不表达已售成本 COGS
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fetch(
        self,
        *,
        from_date: date,
        to_date: date,
    ) -> dict[str, Any]:
        params = {"from_date": from_date, "to_date": to_date}
        summary = await self._summary(params)
        daily = await self._daily(params)
        by_supplier = await self._by_supplier(params)
        by_item = await self._by_item(params)
        return {
            "summary": summary,
            "daily": daily,
            "by_supplier": by_supplier,
            "by_item": by_item,
        }

    async def fetch_sku_purchase_ledger(
        self,
        *,
        from_date: date,
        to_date: date,
        supplier_id: int | None = None,
        item_keyword: str = "",
    ) -> dict[str, Any]:
        keyword = item_keyword.strip()
        params: dict[str, object] = {
            "from_date": from_date,
            "to_date": to_date,
            "item_keyword": keyword,
            "item_keyword_like": f"%{keyword}%",
        }

        supplier_filter = ""
        if supplier_id is not None:
            params["supplier_id"] = int(supplier_id)
            supplier_filter = "AND po.supplier_id = :supplier_id"

        sql = text(
            f"""
            WITH ledger AS (
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

                po.purchase_time AS purchase_time,
                DATE(po.purchase_time) AS purchase_date,

                pol.qty_ordered_input AS qty_ordered_input,
                pol.purchase_uom_name_snapshot AS purchase_uom_name_snapshot,
                pol.purchase_ratio_to_base_snapshot AS purchase_ratio_to_base_snapshot,
                pol.qty_ordered_base AS qty_ordered_base,

                pol.supply_price AS purchase_unit_price,
                {self._line_amount_expr()}::numeric(14, 2) AS planned_line_amount

                FROM purchase_orders po
                JOIN purchase_order_lines pol ON pol.po_id = po.id
               WHERE {self._base_where()}
                 {supplier_filter}
                 AND (
                   :item_keyword = ''
                   OR pol.item_sku ILIKE :item_keyword_like
                   OR pol.item_name ILIKE :item_keyword_like
                   OR pol.spec_text ILIKE :item_keyword_like
                   OR CAST(pol.item_id AS text) = :item_keyword
                 )
            ),
            weighted AS (
              SELECT
                ledger.*,
                SUM(ledger.planned_line_amount) OVER (
                  PARTITION BY ledger.item_id
                ) AS item_purchase_amount,
                SUM(ledger.qty_ordered_base) OVER (
                  PARTITION BY ledger.item_id
                ) AS item_base_qty
              FROM ledger
            )
            SELECT
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
              purchase_time,
              purchase_date,
              qty_ordered_input,
              purchase_uom_name_snapshot,
              purchase_ratio_to_base_snapshot,
              qty_ordered_base,
              purchase_unit_price,
              planned_line_amount,
              CASE
                WHEN item_base_qty > 0
                THEN (item_purchase_amount / item_base_qty)::numeric(14, 4)
                ELSE NULL
              END AS accounting_unit_price
            FROM weighted
            ORDER BY
              item_sku ASC NULLS LAST,
              item_id ASC,
              purchase_time DESC,
              po_id DESC,
              line_no ASC,
              po_line_id ASC
            LIMIT 500
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()

        return {
            "rows": [
                {
                    "po_line_id": int(row["po_line_id"]),
                    "po_id": int(row["po_id"]),
                    "po_no": str(row["po_no"]),
                    "line_no": int(row["line_no"]),
                    "item_id": int(row["item_id"]),
                    "item_sku": row["item_sku"],
                    "item_name": row["item_name"],
                    "spec_text": row["spec_text"],
                    "supplier_id": int(row["supplier_id"]),
                    "supplier_name": str(row["supplier_name"] or ""),
                    "purchase_time": row["purchase_time"],
                    "purchase_date": row["purchase_date"],
                    "qty_ordered_input": int(row["qty_ordered_input"] or 0),
                    "purchase_uom_name_snapshot": str(
                        row["purchase_uom_name_snapshot"] or ""
                    ),
                    "purchase_ratio_to_base_snapshot": int(
                        row["purchase_ratio_to_base_snapshot"] or 0
                    ),
                    "qty_ordered_base": int(row["qty_ordered_base"] or 0),
                    "purchase_unit_price": (
                        to_decimal(row["purchase_unit_price"])
                        if row["purchase_unit_price"] is not None
                        else None
                    ),
                    "planned_line_amount": to_decimal(row["planned_line_amount"]),
                    "accounting_unit_price": (
                        to_decimal(row["accounting_unit_price"])
                        if row["accounting_unit_price"] is not None
                        else None
                    ),
                }
                for row in rows
            ]
        }

    def _base_where(self) -> str:
        return """
        DATE(po.purchase_time) BETWEEN :from_date AND :to_date
        AND NOT EXISTS (
          SELECT 1
            FROM item_test_set_items its
            JOIN item_test_sets ts ON ts.id = its.set_id
           WHERE ts.code = 'DEFAULT'
             AND its.item_id = pol.item_id
        )
        """

    def _line_amount_expr(self) -> str:
        return """
        (
          COALESCE(pol.supply_price, 0) * COALESCE(pol.qty_ordered_base, 0)
        )
        """

    async def _summary(self, params: dict[str, object]) -> dict[str, object]:
        sql = text(
            f"""
            SELECT
              COUNT(DISTINCT po.id) AS purchase_order_count,
              COUNT(DISTINCT po.supplier_id) AS supplier_count,
              COUNT(DISTINCT pol.item_id) AS item_count,
              COALESCE(SUM({self._line_amount_expr()}), 0) AS purchase_amount,
              COALESCE(SUM(COALESCE(pol.qty_ordered_base, 0)), 0) AS total_units
              FROM purchase_orders po
              JOIN purchase_order_lines pol ON pol.po_id = po.id
             WHERE {self._base_where()}
            """
        )
        row = (await self.session.execute(sql, params)).mappings().one()
        purchase_amount = to_decimal(row["purchase_amount"])
        total_units = to_decimal(row["total_units"])
        return {
            "purchase_order_count": int(row["purchase_order_count"] or 0),
            "supplier_count": int(row["supplier_count"] or 0),
            "item_count": int(row["item_count"] or 0),
            "purchase_amount": purchase_amount,
            "avg_unit_cost": ratio(purchase_amount, total_units),
        }

    async def _daily(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            WITH day_dim AS (
              SELECT generate_series(:from_date, :to_date, interval '1 day')::date AS day
            ),
            agg AS (
              SELECT
                DATE(po.purchase_time) AS day,
                COUNT(DISTINCT po.id) AS purchase_order_count,
                COALESCE(SUM({self._line_amount_expr()}), 0) AS purchase_amount
                FROM purchase_orders po
                JOIN purchase_order_lines pol ON pol.po_id = po.id
               WHERE {self._base_where()}
               GROUP BY DATE(po.purchase_time)
            )
            SELECT
              d.day,
              COALESCE(a.purchase_order_count, 0) AS purchase_order_count,
              COALESCE(a.purchase_amount, 0) AS purchase_amount
              FROM day_dim d
              LEFT JOIN agg a ON a.day = d.day
             ORDER BY d.day ASC
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        return [
            {
                "day": row["day"],
                "purchase_order_count": int(row["purchase_order_count"] or 0),
                "purchase_amount": to_decimal(row["purchase_amount"]),
            }
            for row in rows
        ]

    async def _by_supplier(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              po.supplier_id,
              COALESCE(po.supplier_name, '') AS supplier_name,
              COUNT(DISTINCT po.id) AS purchase_order_count,
              COALESCE(SUM({self._line_amount_expr()}), 0) AS purchase_amount,
              COALESCE(SUM(COALESCE(pol.qty_ordered_base, 0)), 0) AS total_units
              FROM purchase_orders po
              JOIN purchase_order_lines pol ON pol.po_id = po.id
             WHERE {self._base_where()}
             GROUP BY po.supplier_id, COALESCE(po.supplier_name, '')
             ORDER BY purchase_amount DESC, supplier_name ASC
             LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        out: list[dict[str, object]] = []
        for row in rows:
            purchase_amount = to_decimal(row["purchase_amount"])
            total_units = to_decimal(row["total_units"])
            out.append(
                {
                    "supplier_id": int(row["supplier_id"]) if row["supplier_id"] is not None else None,
                    "supplier_name": str(row["supplier_name"] or ""),
                    "purchase_order_count": int(row["purchase_order_count"] or 0),
                    "purchase_amount": purchase_amount,
                    "avg_unit_cost": ratio(purchase_amount, total_units),
                }
            )
        return out

    async def _by_item(self, params: dict[str, object]) -> list[dict[str, object]]:
        sql = text(
            f"""
            SELECT
              pol.item_id,
              MAX(pol.item_sku) AS item_sku,
              MAX(pol.item_name) AS item_name,
              COALESCE(SUM(COALESCE(pol.qty_ordered_base, 0)), 0) AS total_units,
              COALESCE(SUM({self._line_amount_expr()}), 0) AS purchase_amount
              FROM purchase_orders po
              JOIN purchase_order_lines pol ON pol.po_id = po.id
             WHERE {self._base_where()}
             GROUP BY pol.item_id
             ORDER BY purchase_amount DESC, pol.item_id ASC
             LIMIT 100
            """
        )
        rows = (await self.session.execute(sql, params)).mappings().all()
        out: list[dict[str, object]] = []
        for row in rows:
            purchase_amount = to_decimal(row["purchase_amount"])
            total_units = to_decimal(row["total_units"])
            out.append(
                {
                    "item_id": int(row["item_id"]),
                    "item_sku": row["item_sku"],
                    "item_name": row["item_name"],
                    "total_units": int(row["total_units"] or 0),
                    "purchase_amount": purchase_amount,
                    "avg_unit_cost": ratio(purchase_amount, total_units),
                }
            )
        return out
