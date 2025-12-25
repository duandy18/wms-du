# app/api/routers/finance_overview_routes_shop.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session
from app.api.routers.finance_overview_helpers import (
    clean_platform,
    clean_shop_id,
    ensure_default_7d_range,
    parse_date_param,
)
from app.api.routers.finance_overview_schemas import FinanceShopRow


def register(router: APIRouter) -> None:
    # ---------------------------------------------------------------------------
    # /finance/shop
    # ---------------------------------------------------------------------------

    @router.get(
        "/shop",
        response_model=List[FinanceShopRow],
        summary="按店铺聚合的收入 / 成本 / 毛利（运营视角粗粒度）",
    )
    async def finance_by_shop(
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
        shop_id: Optional[str] = Query(
            None,
            description="按店铺 ID 过滤（可选）",
        ),
    ) -> List[FinanceShopRow]:
        """
        店铺盈利能力（粗粒度）：

        - 收入：orders.pay_amount（缺失则退回 order_amount），按平台 / 店铺汇总
        - 商品成本：基于 purchase_order_lines 推导的 avg_unit_cost × order_items.qty
        - 发货成本：shipping_records.cost_estimated，按平台 / 店铺汇总

        说明：
        - plat='' / shop='' 表示“不过滤”，避免 asyncpg 对 NULL 参数类型歧义。
        """
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        from_dt, to_dt = await ensure_default_7d_range(session, from_dt=from_dt, to_dt=to_dt)

        plat = clean_platform(platform)
        shop = clean_shop_id(shop_id)

        sql = text(
            """
            WITH item_cost AS (
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
            order_line_cost_shop AS (
              SELECT
                o.platform,
                o.shop_id,
                SUM(
                  COALESCE(oi.qty, 0) * COALESCE(iac.avg_unit_cost, 0)
                ) AS total_purchase_cost
              FROM orders o
              JOIN order_items oi ON oi.order_id = o.id
              LEFT JOIN item_avg_cost iac ON iac.item_id = oi.item_id
              WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
                AND (:plat = '' OR o.platform = :plat)
                AND (:shop = '' OR o.shop_id = :shop)
              GROUP BY o.platform, o.shop_id
            ),
            order_revenue_shop AS (
              SELECT
                o.platform,
                o.shop_id,
                SUM(
                  COALESCE(o.pay_amount, o.order_amount, 0)
                ) AS total_revenue
              FROM orders o
              WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
                AND (:plat = '' OR o.platform = :plat)
                AND (:shop = '' OR o.shop_id = :shop)
              GROUP BY o.platform, o.shop_id
            ),
            ship_cost_shop AS (
              SELECT
                sr.platform,
                sr.shop_id,
                SUM(COALESCE(sr.cost_estimated, 0)) AS total_shipping_cost
              FROM shipping_records sr
              WHERE DATE(sr.created_at) BETWEEN :from_date AND :to_date
                AND (:plat = '' OR sr.platform = :plat)
                AND (:shop = '' OR sr.shop_id = :shop)
              GROUP BY sr.platform, sr.shop_id
            ),
            shop_dim AS (
              SELECT DISTINCT platform, shop_id FROM order_revenue_shop
              UNION
              SELECT DISTINCT platform, shop_id FROM order_line_cost_shop
              UNION
              SELECT DISTINCT platform, shop_id FROM ship_cost_shop
            )
            SELECT
              sd.platform,
              sd.shop_id,
              COALESCE(orev.total_revenue, 0)       AS revenue,
              COALESCE(oc.total_purchase_cost, 0)   AS purchase_cost,
              COALESCE(sc.total_shipping_cost, 0)   AS shipping_cost
            FROM shop_dim sd
            LEFT JOIN order_revenue_shop   orev
              ON orev.platform = sd.platform AND orev.shop_id = sd.shop_id
            LEFT JOIN order_line_cost_shop oc
              ON oc.platform   = sd.platform AND oc.shop_id   = sd.shop_id
            LEFT JOIN ship_cost_shop       sc
              ON sc.platform   = sd.platform AND sc.shop_id   = sd.shop_id
            ORDER BY sd.platform, sd.shop_id
            """
        )

        result = await session.execute(
            sql,
            {
                "from_date": from_dt,
                "to_date": to_dt,
                "plat": plat,
                "shop": shop,
            },
        )
        rows = result.mappings().all()

        items: List[FinanceShopRow] = []
        for row in rows:
            platform_val = str(row["platform"])
            shop_val = str(row["shop_id"])

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
                FinanceShopRow(
                    platform=platform_val,
                    shop_id=shop_val,
                    revenue=revenue,
                    purchase_cost=purchase_cost,
                    shipping_cost=shipping_cost,
                    gross_profit=gross_profit,
                    gross_margin=gross_margin,
                    fulfillment_ratio=fulfillment_ratio,
                )
            )

        return items
