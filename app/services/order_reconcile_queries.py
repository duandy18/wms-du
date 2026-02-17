# app/services/order_reconcile_queries.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_ref_helper import make_order_ref


async def load_order_head(session: AsyncSession, order_id: int) -> Optional[dict]:
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    id,
                    platform,
                    shop_id,
                    ext_order_no
                  FROM orders
                 WHERE id = :oid
                 LIMIT 1
                """
                ),
                {"oid": order_id},
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row else None


async def load_items(session: AsyncSession, order_id: int) -> Dict[int, dict]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    item_id,
                    sku_id,
                    title,
                    COALESCE(qty, 0) AS qty
                  FROM order_items
                 WHERE order_id = :oid
                """
                ),
                {"oid": order_id},
            )
        )
        .mappings()
        .all()
    )
    result: Dict[int, dict] = {}
    for r in rows:
        item_id = int(r["item_id"])
        result[item_id] = {
            "sku_id": r.get("sku_id"),
            "title": r.get("title"),
            "qty_ordered": int(r.get("qty") or 0),
        }
    return result


async def load_shipped(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Dict[int, int]:
    order_ref = make_order_ref(platform, shop_id, ext_order_no)
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    item_id,
                    SUM(
                        CASE WHEN delta < 0 THEN -delta ELSE 0 END
                    ) AS shipped_qty
                  FROM stock_ledger
                 WHERE ref = :ref
                 GROUP BY item_id
                """
                ),
                {"ref": order_ref},
            )
        )
        .mappings()
        .all()
    )
    result: Dict[int, int] = {}
    for r in rows:
        result[int(r["item_id"])] = int(r.get("shipped_qty") or 0)
    return result


async def load_returned(session: AsyncSession, order_id: int) -> Dict[int, int]:
    """
    returned 终态口径：Receipt(CONFIRMED) -> ReceiptLines.qty_received
    - inbound_receipts.source_type='ORDER'
    - inbound_receipts.source_id = order_id
    - inbound_receipts.status='CONFIRMED'
    - 汇总 inbound_receipt_lines.qty_received 按 item_id 聚合
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    rl.item_id,
                    SUM(COALESCE(rl.qty_received, 0)) AS returned_qty
                  FROM inbound_receipt_lines AS rl
                  JOIN inbound_receipts AS r
                    ON r.id = rl.receipt_id
                 WHERE r.source_type = 'ORDER'
                   AND r.source_id = :oid
                   AND r.status = 'CONFIRMED'
                 GROUP BY rl.item_id
                """
                ),
                {"oid": order_id},
            )
        )
        .mappings()
        .all()
    )
    result: Dict[int, int] = {}
    for r in rows:
        result[int(r["item_id"])] = int(r.get("returned_qty") or 0)
    return result


async def list_order_ids_by_created_at(
    session: AsyncSession,
    *,
    time_from: datetime,
    time_to: datetime,
    limit: int = 1000,
) -> List[int]:
    rows = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM orders
                 WHERE created_at >= :from_ts
                   AND created_at <= :to_ts
                 ORDER BY created_at, id
                 LIMIT :limit
                """
            ),
            {
                "from_ts": time_from,
                "to_ts": time_to,
                "limit": limit,
            },
        )
    ).fetchall()
    return [int(r[0]) for r in rows]
