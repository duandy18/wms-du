# app/api/routers/orders_stats.py
from __future__ import annotations

from datetime import date as _date
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session

router = APIRouter(
    prefix="/orders/stats",
    tags=["orders-stats"],
)


class OrdersDailyStatsModel(BaseModel):
    """单日汇总：创建 / 发货 / 退货 订单数"""

    # 注意：类型用 _date，字段名仍然叫 date，避免和 datetime.date 类型同名
    date: _date = Field(..., description="统计日期（UTC，自然日）")
    platform: Optional[str] = Field(
        None,
        description="可选平台过滤（如 PDD），大写",
    )
    shop_id: Optional[str] = Field(
        None,
        description="可选店铺过滤（字符串，与 orders.shop_id 一致）",
    )
    orders_created: int = Field(..., description="当天创建的订单数量")
    orders_shipped: int = Field(
        ..., description="当天发货的订单数量（按 ref=ORD:* 的 distinct ref 计）"
    )
    orders_returned: int = Field(
        ..., description="当天有退货入库的订单数量（source_type=ORDER 的收货任务）"
    )


class OrdersDailyTrendItem(BaseModel):
    date: _date
    orders_created: int
    orders_shipped: int
    orders_returned: int
    return_rate: float = Field(
        ...,
        description="退货率 = orders_returned / orders_shipped（若分母为 0 则为 0.0）",
    )


class OrdersTrendResponseModel(BaseModel):
    days: List[OrdersDailyTrendItem] = Field(
        default_factory=list,
        description="按日期升序排列的 7 天趋势",
    )


async def _calc_daily_stats(
    session: AsyncSession,
    *,
    day: _date,
    platform: Optional[str],
    shop_id: Optional[str],
) -> tuple[int, int, int]:
    """
    计算单日的：
    - 创建订单数（orders.created_at）
    - 发货订单数（ledger 中 ref=ORD:* 且 delta<0 的 distinct ref）
    - 退货订单数（receive_tasks.source_type='ORDER' 且 COMMITTED 的 distinct source_id）
    """
    # 统一按 UTC 自然日计算
    start = datetime.combine(day, time(0, 0, 0), tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    plat = platform.upper().strip() if platform else None

    # ---- created: 直接查 orders ----
    clauses = ["created_at >= :start", "created_at < :end"]
    params: dict = {"start": start, "end": end}

    if plat:
        clauses.append("platform = :p")
        params["p"] = plat
    if shop_id:
        clauses.append("shop_id = :s")
        params["s"] = shop_id

    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql_created = f"""
        SELECT COUNT(*) AS c
          FROM orders
          {where_sql}
    """
    created_res = await session.execute(text(sql_created), params)
    orders_created = int(created_res.scalar() or 0)

    # ---- shipped: 查 stock_ledger（ref=ORD:*，delta<0，按 ref 去重）----
    params2: dict = {"start": start, "end": end}
    shipped_clauses = [
        "occurred_at >= :start",
        "occurred_at < :end",
        "delta < 0",
    ]

    # ref 过滤：ORD:{PLAT}:{shop_id}:{ext_order_no}
    if plat and shop_id:
        shipped_clauses.append("ref LIKE :ref_prefix")
        params2["ref_prefix"] = f"ORD:{plat}:{shop_id}:%"
    elif plat:
        shipped_clauses.append("ref LIKE :ref_prefix")
        params2["ref_prefix"] = f"ORD:{plat}:%"
    else:
        shipped_clauses.append("ref LIKE 'ORD:%'")

    where_sql2 = "WHERE " + " AND ".join(shipped_clauses)
    sql_shipped = f"""
        SELECT COUNT(DISTINCT ref) AS c
          FROM stock_ledger
          {where_sql2}
    """
    shipped_res = await session.execute(text(sql_shipped), params2)
    orders_shipped = int(shipped_res.scalar() or 0)

    # ---- returned: 查 source_type='ORDER' 的 receive_tasks，并关联 orders ----
    params3: dict = {"start": start, "end": end}
    returned_clauses = [
        "rt.source_type = 'ORDER'",
        "rt.status = 'COMMITTED'",
        "rt.created_at >= :start",
        "rt.created_at < :end",
    ]
    if plat:
        returned_clauses.append("o.platform = :p")
        params3["p"] = plat
    if shop_id:
        returned_clauses.append("o.shop_id = :s")
        params3["s"] = shop_id

    where_sql3 = "WHERE " + " AND ".join(returned_clauses)
    sql_returned = f"""
        SELECT COUNT(DISTINCT rt.source_id) AS c
          FROM receive_tasks AS rt
          JOIN orders AS o
            ON o.id = rt.source_id
          {where_sql3}
    """
    returned_res = await session.execute(text(sql_returned), params3)
    orders_returned = int(returned_res.scalar() or 0)

    return orders_created, orders_shipped, orders_returned


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
    created, shipped, returned = await _calc_daily_stats(
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
        created, shipped, returned = await _calc_daily_stats(
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
