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
    - 退货订单数（Receipt 口径：inbound_receipts.source_type='ORDER' 且 status='CONFIRMED' 的 distinct source_id）

    ✅ PROD-only（简化口径）：
    - 排除测试店铺（platform_test_shops.code='DEFAULT'，以 store_id 为事实锚点）
    """
    # 统一按 UTC 自然日计算
    start = datetime.combine(day, time(0, 0, 0), tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    plat = platform.upper().strip() if platform else None

    # ----------------- created: orders -----------------
    clauses = ["created_at >= :start", "created_at < :end"]
    params: dict = {"start": start, "end": end}

    if plat:
        clauses.append("platform = :p")
        params["p"] = plat
    if shop_id:
        clauses.append("shop_id = :s")
        params["s"] = shop_id

    # PROD-only：测试店铺门禁（store_id）
    clauses.append(
        """
        NOT EXISTS (
          SELECT 1
            FROM stores s
            JOIN platform_test_shops pts
              ON pts.store_id = s.id
             AND pts.code = 'DEFAULT'
           WHERE upper(s.platform) = upper(orders.platform)
             AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(orders.shop_id AS text))
        )
        """.strip()
    )

    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql_created = f"""
        SELECT COUNT(*) AS c
          FROM orders
          {where_sql}
    """
    created_res = await session.execute(text(sql_created), params)
    orders_created = int(created_res.scalar() or 0)

    # ----------------- shipped: stock_ledger -> parse ref -> join orders -----------------
    # ref 形态：ORD:{PLAT}:{shop_id}:{ext_order_no...}
    # 用 split_part/regexp_replace 解析后 join orders(platform, shop_id, ext_order_no)
    shipped_clauses = [
        "l.occurred_at >= :start",
        "l.occurred_at < :end",
        "l.delta < 0",
        "l.ref LIKE 'ORD:%'",
    ]
    params2: dict = {"start": start, "end": end}

    if plat:
        shipped_clauses.append("upper(o.platform) = :p")
        params2["p"] = plat
    if shop_id:
        shipped_clauses.append("btrim(CAST(o.shop_id AS text)) = btrim(CAST(:s AS text))")
        params2["s"] = shop_id

    # PROD-only：测试店铺门禁（store_id）
    shipped_clauses.append(
        """
        NOT EXISTS (
          SELECT 1
            FROM stores s
            JOIN platform_test_shops pts
              ON pts.store_id = s.id
             AND pts.code = 'DEFAULT'
           WHERE upper(s.platform) = upper(o.platform)
             AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(o.shop_id AS text))
        )
        """.strip()
    )

    where_sql2 = "WHERE " + " AND ".join(shipped_clauses)
    sql_shipped = f"""
        SELECT COUNT(DISTINCT l.ref) AS c
          FROM stock_ledger l
          JOIN orders o
            ON upper(o.platform) = upper(split_part(l.ref, ':', 2))
           AND btrim(CAST(o.shop_id AS text)) = btrim(split_part(l.ref, ':', 3))
           AND btrim(CAST(o.ext_order_no AS text)) = btrim(regexp_replace(l.ref, '^ORD:[^:]+:[^:]+:', ''))
          {where_sql2}
    """
    shipped_res = await session.execute(text(sql_shipped), params2)
    orders_shipped = int(shipped_res.scalar() or 0)

    # ----------------- returned: inbound_receipts JOIN orders -----------------
    # Receipt 终态口径：
    # - source_type='ORDER'
    # - status='CONFIRMED'
    # - occurred_at 落在自然日内（事实发生时间）
    params3: dict = {"start": start, "end": end}
    returned_clauses = [
        "r.source_type = 'ORDER'",
        "r.status = 'CONFIRMED'",
        "r.source_id IS NOT NULL",
        "r.occurred_at >= :start",
        "r.occurred_at < :end",
    ]
    if plat:
        returned_clauses.append("o.platform = :p")
        params3["p"] = plat
    if shop_id:
        returned_clauses.append("o.shop_id = :s")
        params3["s"] = shop_id

    # PROD-only：测试店铺门禁（store_id）
    returned_clauses.append(
        """
        NOT EXISTS (
          SELECT 1
            FROM stores s
            JOIN platform_test_shops pts
              ON pts.store_id = s.id
             AND pts.code = 'DEFAULT'
           WHERE upper(s.platform) = upper(o.platform)
             AND btrim(CAST(s.shop_id AS text)) = btrim(CAST(o.shop_id AS text))
        )
        """.strip()
    )

    where_sql3 = "WHERE " + " AND ".join(returned_clauses)
    sql_returned = f"""
        SELECT COUNT(DISTINCT r.source_id) AS c
          FROM inbound_receipts AS r
          JOIN orders AS o
            ON o.id = r.source_id
          {where_sql3}
    """
    returned_res = await session.execute(text(sql_returned), params3)
    orders_returned = int(returned_res.scalar() or 0)

    return orders_created, orders_shipped, orders_returned
