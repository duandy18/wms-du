# app/api/routers/finance_overview_routes_sku.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.finance_overview_helpers import (
    clean_platform,
    ensure_default_7d_range,
    parse_date_param,
)
from app.api.routers.finance_overview_schemas import FinanceSkuRow


def register(router: APIRouter) -> None:
    # ---------------------------------------------------------------------------
    # /finance/sku  — SKU 毛利榜（不含运费）
    # ---------------------------------------------------------------------------

    @router.get(
        "/sku",
        response_model=List[FinanceSkuRow],
        summary="SKU 毛利榜（不含运费，基于平均进货价）",
    )
    async def finance_by_sku(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: Optional[str] = Query(
            None,
            description="起始日期（YYYY-MM-DD，含）。默认=今天往前 6 天。",
        ),
        to_date: Optional[str] = Query(
            None,
            description="结束日期（YYYY-MM-DD，含）。默认=今天。",
        ),
        platform: Optional[str] = Query(
            None,
            description="按平台过滤，例如 PDD / JD（可选）",
        ),
    ) -> List[FinanceSkuRow]:
        """
        SKU 毛利榜（粗粒度版本）：

        - 商品成本：avg_unit_cost(item_id) × SUM(order_items.qty)
          avg_unit_cost = total_amount / total_units
          total_amount = SUM(qty_ordered_base*supply_price - discount_amount)
          total_units  = SUM(qty_ordered_base)
        """
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        from_dt, to_dt = await ensure_default_7d_range(session, from_dt=from_dt, to_dt=to_dt)

        plat = clean_platform(platform)

        sql = text(
            """
            WITH item_cost AS (
              SELECT
                pol.item_id,
                COALESCE(SUM(
                  (COALESCE(pol.qty_ordered_base, 0) * COALESCE(pol.supply_price, 0))
                  - COALESCE(pol.discount_amount, 0)
                ), 0) AS total_amount,
                COALESCE(SUM(COALESCE(pol.qty_ordered_base, 0)), 0) AS total_units
              FROM purchase_orders po
              JOIN purchase_order_lines pol ON pol.po_id = po.id
              GROUP BY pol.item_id
            ),
            item_avg_cost AS (
              SELECT
                item_id,
                CASE
                  WHEN total_units > 0 THEN total_amount / total_units
                  ELSE NULL
                END AS avg_unit_cost
              FROM item_cost
            ),
            sku_agg AS (
              SELECT
                oi.item_id,
                MAX(oi.sku_id)           AS sku_id,
                MAX(oi.title)            AS title,
                COALESCE(SUM(oi.qty), 0) AS qty_sold,
                SUM(
                  COALESCE(
                    oi.amount,
                    COALESCE(oi.qty, 0) * COALESCE(oi.price, 0)
                  )
                ) AS revenue,
                SUM(
                  COALESCE(oi.qty, 0) * COALESCE(iac.avg_unit_cost, 0)
                ) AS purchase_cost
              FROM orders o
              JOIN order_items oi ON oi.order_id = o.id
              LEFT JOIN item_avg_cost iac ON iac.item_id = oi.item_id
              WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
                AND (:plat = '' OR o.platform = :plat)
              GROUP BY oi.item_id
            )
            SELECT
              item_id,
              sku_id,
              title,
              qty_sold,
              COALESCE(revenue, 0)        AS revenue,
              COALESCE(purchase_cost, 0)  AS purchase_cost
            FROM sku_agg
            WHERE qty_sold > 0
            ORDER BY revenue DESC
            """
        )

        result = await session.execute(
            sql,
            {
                "from_date": from_dt,
                "to_date": to_dt,
                "plat": plat,
            },
        )
        rows = result.mappings().all()

        items: List[FinanceSkuRow] = []
        for row in rows:
            item_id = int(row["item_id"])
            sku_id = row.get("sku_id")
            title = row.get("title")

            qty_sold = int(row["qty_sold"] or 0)
            revenue = Decimal(str(row["revenue"] or 0))
            purchase_cost = Decimal(str(row["purchase_cost"] or 0))

            gross_profit = revenue - purchase_cost

            if revenue > 0:
                gross_margin = (gross_profit / revenue).quantize(Decimal("0.0001"))
            else:
                gross_margin = None

            items.append(
                FinanceSkuRow(
                    item_id=item_id,
                    sku_id=sku_id,
                    title=title,
                    qty_sold=qty_sold,
                    revenue=revenue,
                    purchase_cost=purchase_cost,
                    gross_profit=gross_profit,
                    gross_margin=gross_margin,
                )
            )

        return items
