# app/api/routers/finance_overview_routes_order_unit.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

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
from app.api.routers.finance_overview_schemas import (
    OrderUnitContributionPoint,
    OrderUnitRow,
    OrderUnitSummary,
)


def register(router: APIRouter) -> None:
    # ---------------------------------------------------------------------------
    # /finance/order-unit — 客单价 & 贡献度分析
    # ---------------------------------------------------------------------------

    @router.get(
        "/order-unit",
        summary="客单价 & 贡献度分析（按订单维度）",
    )
    async def finance_order_unit(
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
    ) -> dict:
        """
        客单价 & 贡献度分析：

        - 每一条记录 = 一笔订单（order_value = pay_amount 或 order_amount）
        - summary：订单数 / 总收入 / 平均客单价 / 中位客单价
        - contribution_curve：前 20%/40%/60%/80%/100% 订单贡献的收入占比
        - top_orders：按金额从大到小列出前 N 笔订单
        """
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        from_dt, to_dt = await ensure_default_7d_range(session, from_dt=from_dt, to_dt=to_dt)

        plat = clean_platform(platform)
        shop = clean_shop_id(shop_id)

        sql = text(
            """
            SELECT
              o.id           AS order_id,
              o.platform     AS platform,
              o.shop_id      AS shop_id,
              o.ext_order_no AS ext_order_no,
              COALESCE(o.pay_amount, o.order_amount, 0) AS order_value,
              o.created_at   AS created_at
            FROM orders o
            WHERE DATE(o.created_at) BETWEEN :from_date AND :to_date
              AND (:plat = '' OR o.platform = :plat)
              AND (:shop = '' OR o.shop_id = :shop)
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

        # 没有订单时，直接返回空 summary
        if not rows:
            empty_summary = OrderUnitSummary(
                order_count=0,
                revenue=Decimal("0"),
                avg_order_value=None,
                median_order_value=None,
            )
            return {
                "summary": empty_summary.model_dump(),
                "contribution_curve": [],
                "top_orders": [],
            }

        # 提取 order_value 列表，做排序与统计
        values: list[Decimal] = []
        base_rows: list[OrderUnitRow] = []

        for r in rows:
            order_value = Decimal(str(r["order_value"] or 0))
            values.append(order_value)
            base_rows.append(
                OrderUnitRow(
                    order_id=int(r["order_id"]),
                    platform=str(r["platform"]),
                    shop_id=str(r["shop_id"]),
                    ext_order_no=str(r["ext_order_no"]),
                    order_value=order_value,
                    created_at=r["created_at"].isoformat(),
                )
            )

        order_count = len(values)
        total_revenue = sum(values, Decimal("0"))

        # 平均客单价
        if order_count > 0:
            avg_order_value = (total_revenue / order_count).quantize(Decimal("0.01"))
        else:
            avg_order_value = None

        # 中位数
        values_sorted = sorted(values)
        mid = order_count // 2
        if order_count % 2 == 1:
            median_order_value = values_sorted[mid]
        else:
            median_order_value = (values_sorted[mid - 1] + values_sorted[mid]) / 2
        median_order_value = median_order_value.quantize(Decimal("0.01"))

        summary = OrderUnitSummary(
            order_count=order_count,
            revenue=total_revenue,
            avg_order_value=avg_order_value,
            median_order_value=median_order_value,
        )

        # 贡献度曲线：前 20%/40%/60%/80%/100% 订单贡献的收入占比
        # 按订单金额从大到小排序
        rows_sorted = sorted(base_rows, key=lambda x: x.order_value, reverse=True)
        cum_values: list[Decimal] = []
        running = Decimal("0")
        for r in rows_sorted:
            running += r.order_value
            cum_values.append(running)

        buckets = [0.2, 0.4, 0.6, 0.8, 1.0]
        contribution: list[OrderUnitContributionPoint] = []

        for p in buckets:
            idx = max(0, min(order_count - 1, int(order_count * p) - 1))
            revenue_upto = cum_values[idx]
            percent_rev = float((revenue_upto / total_revenue) if total_revenue > 0 else 0)
            contribution.append(
                OrderUnitContributionPoint(
                    percent_orders=float(p),
                    percent_revenue=percent_rev,
                )
            )

        # top_orders：取前 50 笔大额订单
        top_n = min(50, order_count)
        top_orders = rows_sorted[:top_n]

        return {
            "summary": summary.model_dump(),
            "contribution_curve": [pt.model_dump() for pt in contribution],
            "top_orders": [o.model_dump() for o in top_orders],
        }
