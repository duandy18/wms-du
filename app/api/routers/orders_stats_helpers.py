# app/api/routers/orders_stats_helpers.py
from __future__ import annotations

from datetime import date as _date
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def calc_daily_stats(
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
