# app/api/routers/orders_stats_routes.py
from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.orders_stats_helpers import calc_daily_stats
from app.api.routers.orders_stats_schemas import (
    OrdersDailyStatsModel,
    OrdersDailyTrendItem,
    OrdersTrendResponseModel,
)


def register(router: APIRouter) -> None:
    @router.get(
        "/daily",
        response_model=OrdersDailyStatsModel,
    )
    async def get_orders_daily_stats(
        date_value: _date = Query(
            default_factory=_date.today,
            alias="date",
            description="统计日期（默认为今天，UTC 自然日）",
        ),
        platform: Optional[str] = Query(
            None,
            description="可选平台过滤（如 PDD）",
        ),
        shop_id: Optional[str] = Query(
            None,
            description="可选店铺过滤（字符串，与 orders.shop_id 一致）",
        ),
        session: AsyncSession = Depends(get_session),
    ) -> OrdersDailyStatsModel:
        """
        单日订单统计：

        - orders_created  : 当天创建订单数
        - orders_shipped  : 当天发货订单数（ledger ref=ORD:*，delta<0 的 distinct ref）
        - orders_returned : 当天有退货入库的订单数（source_type=ORDER 的收货任务）
        """
        created, shipped, returned = await calc_daily_stats(
            session,
            day=date_value,
            platform=platform,
            shop_id=shop_id,
        )
        plat = platform.upper().strip() if platform else None
        return OrdersDailyStatsModel(
            date=date_value,
            platform=plat,
            shop_id=shop_id,
            orders_created=created,
            orders_shipped=shipped,
            orders_returned=returned,
        )

    @router.get(
        "/last7",
        response_model=OrdersTrendResponseModel,
    )
    async def get_orders_last7_stats(
        platform: Optional[str] = Query(
            None,
            description="可选平台过滤（如 PDD）",
        ),
        shop_id: Optional[str] = Query(
            None,
            description="可选店铺过滤",
        ),
        session: AsyncSession = Depends(get_session),
    ) -> OrdersTrendResponseModel:
        """
        近 7 天订单趋势：

        - 每天：orders_created / orders_shipped / orders_returned / return_rate
        - 日期按升序排列（最早在前）
        """
        today = _date.today()
        plat = platform.upper().strip() if platform else None

        days: List[OrdersDailyTrendItem] = []
        # 从 6 天前到今天（共 7 天）
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            created, shipped, returned = await calc_daily_stats(
                session,
                day=d,
                platform=plat,
                shop_id=shop_id,
            )
            rate = float(returned / shipped) if shipped > 0 else 0.0
            days.append(
                OrdersDailyTrendItem(
                    date=d,
                    orders_created=created,
                    orders_shipped=shipped,
                    orders_returned=returned,
                    return_rate=rate,
                )
            )

        return OrdersTrendResponseModel(days=days)
