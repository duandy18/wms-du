# app/api/routers/orders_sla_stats_routes.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_sla_stats_helpers import normalize_window
from app.api.routers.orders_sla_stats_schemas import OrdersSlaStatsModel


def register(router: APIRouter) -> None:
    @router.get(
        "/sla",
        response_model=OrdersSlaStatsModel,
    )
    async def get_orders_sla_stats(
        time_from: Optional[datetime] = Query(
            None,
            description="起始时间（含），用于过滤发货时间 outbound_commits_v2.created_at",
        ),
        time_to: Optional[datetime] = Query(
            None,
            description="结束时间（含），用于过滤发货时间 outbound_commits_v2.created_at",
        ),
        platform: Optional[str] = Query(
            None,
            description="可选平台过滤（如 PDD），大写/小写均可",
        ),
        shop_id: Optional[str] = Query(
            None,
            description="可选店铺过滤（字符串，与 orders.shop_id 一致）",
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
        - 以 outbound_commits_v2.created_at 为发货时间（state=COMPLETED）；
        - 两表通过 trace_id 关联。

        只统计在给定时间窗口内发货的订单（按 outbound_commits_v2.created_at 过滤）。
        """
        start, end = normalize_window(time_from, time_to)

        plat = platform.upper().strip() if platform else None

        base_sql = """
        WITH shipped AS (
          SELECT
            o.id                    AS order_id,
            o.platform              AS platform,
            o.shop_id               AS shop_id,
            o.created_at            AS created_at,
            oc.created_at           AS shipped_at,
            EXTRACT(EPOCH FROM (oc.created_at - o.created_at)) / 3600.0
                                    AS latency_hours
          FROM orders AS o
          JOIN outbound_commits_v2 AS oc
            ON oc.trace_id = o.trace_id
          WHERE oc.state = 'COMPLETED'
            AND oc.created_at >= :start
            AND oc.created_at <= :end
        {plat_clause}
        {shop_clause}
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
        shop_clause = ""

        if plat:
            plat_clause = "  AND o.platform = :p"
            params["p"] = plat
        if shop_id:
            shop_clause = "  AND o.shop_id = :s"
            params["s"] = shop_id

        sql = base_sql.format(
            plat_clause=plat_clause,
            shop_clause=shop_clause,
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
