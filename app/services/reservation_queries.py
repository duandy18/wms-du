# app/services/reservation_queries.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_by_key(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    warehouse_id: int,
    ref: str,
) -> Optional[Tuple[int, str]]:
    """
    根据业务键获取 reservation 的 (id, status)。
    """
    res = await session.execute(
        text(
            """
            SELECT id, status
              FROM reservations
             WHERE platform = :platform
               AND shop_id = :shop_id
               AND warehouse_id = :warehouse_id
               AND ref = :ref
             LIMIT 1
            """
        ),
        {
            "platform": platform,
            "shop_id": shop_id,
            "warehouse_id": warehouse_id,
            "ref": ref,
        },
    )
    row = res.first()
    if row is None:
        return None
    return int(row[0]), str(row[1])


async def get_lines(
    session: AsyncSession,
    reservation_id: int,
) -> List[Tuple[int, int]]:
    """
    获取某张 reservation 的明细行 (item_id, qty) 列表。
    """
    res = await session.execute(
        text(
            """
            SELECT item_id, qty
              FROM reservation_lines
             WHERE reservation_id = :rid
             ORDER BY ref_line ASC
            """
        ),
        {"rid": reservation_id},
    )
    return [(int(r[0]), int(r[1])) for r in res.fetchall()]


async def find_expired(
    session: AsyncSession,
    *,
    now: Optional[datetime] = None,
    limit: int = 100,
) -> List[int]:
    """
    查找已过期但仍为 open 的 reservation.id 列表，用于 TTL worker。
    """
    now = now or datetime.now(timezone.utc)
    res = await session.execute(
        text(
            """
            SELECT id
              FROM reservations
             WHERE status = 'open'
               AND expire_at IS NOT NULL
               AND expire_at < :now
             ORDER BY expire_at ASC, id ASC
             LIMIT :limit
            """
        ),
        {"now": now, "limit": limit},
    )
    return [int(r[0]) for r in res.fetchall()]
