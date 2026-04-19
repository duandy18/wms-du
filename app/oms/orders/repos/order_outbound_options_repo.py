# app/oms/orders/repos/order_outbound_options_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _normalize_text(value: Optional[str]) -> Optional[str]:
    raw = str(value or "").strip()
    return raw or None


async def list_order_outbound_options(
    session: AsyncSession,
    *,
    q: Optional[str],
    platform: Optional[str],
    shop_id: Optional[str],
    limit: int,
    offset: int,
) -> Dict[str, Any]:
    """
    订单出库页：读取订单选择器列表（来源真相 = orders）

    说明：
    - 只查真实 orders 表
    - 不混平台 ledger / fulfillment / wms 执行事实
    - 仅返回“选单”需要的最小字段
    """

    q_norm = _normalize_text(q)
    platform_norm = _normalize_text(platform)
    shop_id_norm = _normalize_text(shop_id)

    clauses: List[str] = []
    params: Dict[str, Any] = {
        "limit": int(limit),
        "offset": int(offset),
    }

    if platform_norm is not None:
        clauses.append("UPPER(platform) = UPPER(:platform)")
        params["platform"] = platform_norm

    if shop_id_norm is not None:
        clauses.append("shop_id = :shop_id")
        params["shop_id"] = shop_id_norm

    if q_norm is not None:
        clauses.append(
            """
            (
              ext_order_no ILIKE :q_like
              OR COALESCE(buyer_name, '') ILIKE :q_like
              OR CAST(id AS TEXT) = :q_exact
            )
            """
        )
        params["q_like"] = f"%{q_norm}%"
        params["q_exact"] = q_norm

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    total_stmt = text(
        f"""
        SELECT COUNT(*) AS total
        FROM orders
        {where_sql}
        """
    )

    rows_stmt = text(
        f"""
        SELECT
          id,
          platform,
          shop_id,
          ext_order_no,
          status,
          buyer_name,
          created_at
        FROM orders
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT :limit
        OFFSET :offset
        """
    )

    total = (await session.execute(total_stmt, params)).scalar_one()

    rows = (await session.execute(rows_stmt, params)).mappings().all()

    return {
        "items": [dict(r) for r in rows],
        "total": int(total or 0),
        "limit": int(limit),
        "offset": int(offset),
    }
