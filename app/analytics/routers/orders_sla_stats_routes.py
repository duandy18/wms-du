# app/analytics/routers/orders_sla_stats_routes.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.analytics.helpers.orders_sla_stats import normalize_window
from app.analytics.contracts.orders_sla_stats import OrdersSlaStatsModel


router = APIRouter(prefix="/orders/stats", tags=["orders-sla"])


def register(router: APIRouter) -> None:
    @router.get(
        "/sla",
        response_model=OrdersSlaStatsModel,
    )
    async def get_orders_sla_stats(
        time_from: Optional[datetime] = Query(
            None,
            description="起始时间（含），用于过滤发货完成时间 order_fulfillment.shipped_at",
        ),
        time_to: Optional[datetime] = Query(
            None,
            description="结束时间（含），用于过滤发货完成时间 order_fulfillment.shipped_at",
        ),
        platform: Optional[str] = Query(
            None,
            description="可选平台过滤（如 PDD），大写/小写均可",
        ),
        store_code: Optional[str] = Query(
            None,
            description="可选店铺过滤（字符串，与 orders.store_code 一致）",
        ),
        sla_hours: float = Query(
            24.0,
            ge=0.0,
            description="SLA 阈值（小时），用于判断是否准时发货，默认 24 小时",
        ),
        session: AsyncSession = Depends(get_session),
    ) -> OrdersSlaStatsModel:
        """
        订单发货 SLA 统计：

        - 以 orders.created_at 为下单时间；
        - 以 order_fulfillment.shipped_at 为发货完成时间；
        - 通过 order_fulfillment.order_id 关联 orders.id。

        只统计在给定时间窗口内发货的订单（按 order_fulfillment.shipped_at 过滤）。

        ✅ PROD-only（简化口径）：
        - 排除测试店铺（platform_test_stores.code='DEFAULT'，以 store_id 为事实锚点）
        """
        start, end = normalize_window(time_from, time_to)

        plat = platform.upper().strip() if platform else None

        base_sql = """
        WITH shipped AS (
          SELECT
            o.id                    AS order_id,
            o.platform              AS platform,
            o.store_code               AS store_code,
            o.created_at            AS created_at,
            f.shipped_at            AS shipped_at,
            EXTRACT(EPOCH FROM (f.shipped_at - o.created_at)) / 3600.0
                                    AS latency_hours
          FROM orders AS o
          JOIN order_fulfillment AS f
            ON f.order_id = o.id
          WHERE f.shipped_at IS NOT NULL
            AND f.shipped_at >= :start
            AND f.shipped_at <= :end

            -- ----------------- PROD-only：测试店铺门禁（store_id 级别） -----------------
            AND NOT EXISTS (
              SELECT 1
                FROM platform_test_stores pts
               WHERE pts.store_id = o.store_id
                 AND pts.code = 'DEFAULT'
            )
        {plat_clause}
        {store_clause}
        )
        SELECT
          COUNT(*)                         AS total_orders,
          AVG(latency_hours)              AS avg_hours,
          percentile_disc(0.95)
            WITHIN GROUP (ORDER BY latency_hours) AS p95_hours,
          COUNT(*) FILTER (WHERE latency_hours <= :sla_hours)
                                          AS on_time_orders
        FROM shipped
        """

        params: dict[str, object] = {
            "start": start,
            "end": end,
            "sla_hours": sla_hours,
        }

        plat_clause = ""
        store_clause = ""

        if plat:
            plat_clause = "  AND o.platform = :p"
            params["p"] = plat
        if store_code:
            store_clause = "  AND o.store_code = :s"
            params["s"] = store_code

        sql = base_sql.format(
            plat_clause=plat_clause,
            store_clause=store_clause,
        )

        res = await session.execute(text(sql), params)
        row = res.mappings().first()

        if not row:
            return OrdersSlaStatsModel(
                total_orders=0,
                avg_ship_hours=None,
                p95_ship_hours=None,
                on_time_orders=0,
                on_time_rate=0.0,
            )

        total_orders = int(row["total_orders"] or 0)
        avg_hours = float(row["avg_hours"]) if row["avg_hours"] is not None else None
        p95_hours = float(row["p95_hours"]) if row["p95_hours"] is not None else None
        on_time_orders = int(row["on_time_orders"] or 0)

        on_time_rate = float(on_time_orders / total_orders) if total_orders > 0 else 0.0

        return OrdersSlaStatsModel(
            total_orders=total_orders,
            avg_ship_hours=avg_hours,
            p95_ship_hours=p95_hours,
            on_time_orders=on_time_orders,
            on_time_rate=on_time_rate,
        )

register(router)

__all__ = ["router", "register"]
