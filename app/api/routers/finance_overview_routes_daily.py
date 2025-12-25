# app/api/routers/finance_overview_routes_daily.py
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.finance_overview_helpers import ensure_default_7d_range, parse_date_param
from app.api.routers.finance_overview_schemas import FinanceDailyRow


def register(router: APIRouter) -> None:
    # ---------------------------------------------------------------------------
    # /finance/overview/daily
    # ---------------------------------------------------------------------------

    @router.get(
        "/overview/daily",
        response_model=List[FinanceDailyRow],
        summary="按日汇总的收入 / 成本 / 毛利趋势（运营视角粗粒度）",
    )
    async def finance_overview_daily(
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
    ) -> List[FinanceDailyRow]:
        """
        财务总览（按日）——运营视角粗估版本：

        - 收入：orders.pay_amount（缺失则退回 order_amount），按 orders.created_at::date 汇总
        - 商品成本：以 purchase_order_lines 的平均单价（总金额 / 总最小单位数）粗算，
                    再乘以 order_items.qty（忽略退货与发货时点，只按订单创建日统计）
        - 发货成本：shipping_records.cost_estimated，按 shipping_records.created_at::date 汇总
        """
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        from_dt, to_dt = await ensure_default_7d_range(session, from_dt=from_dt, to_dt=to_dt)

        sql = text(
            """
            WITH day_dim AS (
              SELECT generate_series(:from_date, :to_date, interval '1 day')::date AS day
            ),
            item_cost AS (
              SELECT
                pol.item_id,
                COALESCE(SUM(COALESCE(pol.line_amount, 0)), 0) AS total_amount,
                COALESCE(SUM(pol.qty_ordered * COALESCE(pol.units_per_case, 1)), 0) AS total_units
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
            order_line_cost AS (
              SELECT
                DATE(o.created_at) AS day,
                SUM(
                  COALESCE(oi.qty, 0) * COALESCE(iac.avg_unit_cost, 0)
                ) AS total_purchase_cost
              FROM orders o
              JOIN order_items oi ON oi.order_id = o.id
              LEFT JOIN item_avg_cost iac ON iac.item_id = oi.item_id
              WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
              GROUP BY DATE(o.created_at)
            ),
            order_revenue AS (
              SELECT
                DATE(o.created_at) AS day,
                SUM(
                  COALESCE(o.pay_amount, o.order_amount, 0)
                ) AS total_revenue
              FROM orders o
              WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
              GROUP BY DATE(o.created_at)
            ),
            ship_cost AS (
              SELECT
                DATE(created_at) AS day,
                SUM(COALESCE(cost_estimated, 0)) AS total_shipping_cost
              FROM shipping_records
              WHERE DATE(created_at) BETWEEN :from_date AND :to_date
              GROUP BY DATE(created_at)
            )
            SELECT
              d.day AS day,
              COALESCE(orev.total_revenue, 0)       AS revenue,
              COALESCE(oc.total_purchase_cost, 0)   AS purchase_cost,
              COALESCE(sc.total_shipping_cost, 0)   AS shipping_cost
            FROM day_dim d
            LEFT JOIN order_revenue   orev ON orev.day = d.day
            LEFT JOIN order_line_cost oc   ON oc.day   = d.day
            LEFT JOIN ship_cost       sc   ON sc.day   = d.day
            ORDER BY d.day ASC
            """
        )

        result = await session.execute(
            sql,
            {
                "from_date": from_dt,
                "to_date": to_dt,
            },
        )
        rows = result.mappings().all()

        items: List[FinanceDailyRow] = []
        for row in rows:
            day: date = row["day"]
            revenue = Decimal(str(row["revenue"] or 0))
            purchase_cost = Decimal(str(row["purchase_cost"] or 0))
            shipping_cost = Decimal(str(row["shipping_cost"] or 0))

            gross_profit = revenue - purchase_cost - shipping_cost

            if revenue > 0:
                gross_margin = (gross_profit / revenue).quantize(Decimal("0.0001"))
                fulfillment_ratio = (shipping_cost / revenue).quantize(
                    Decimal("0.0001"),
                )
            else:
                gross_margin = None
                fulfillment_ratio = None

            items.append(
                FinanceDailyRow(
                    day=day,
                    revenue=revenue,
                    purchase_cost=purchase_cost,
                    shipping_cost=shipping_cost,
                    gross_profit=gross_profit,
                    gross_margin=gross_margin,
                    fulfillment_ratio=fulfillment_ratio,
                )
            )

        return items
