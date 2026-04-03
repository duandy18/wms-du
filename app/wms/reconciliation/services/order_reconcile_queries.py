# app/wms/reconciliation/services/order_reconcile_queries.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_order_ids_by_created_at(
    session: AsyncSession,
    *,
    time_from: datetime,
    time_to: datetime,
    limit: int = 1000,
) -> List[int]:
    """
    按 orders.created_at 时间窗列出订单 id（用于批量对账）。
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM orders
                 WHERE created_at >= :f
                   AND created_at <  :t
                 ORDER BY created_at ASC, id ASC
                 LIMIT :lim
                """
            ),
            {"f": time_from, "t": time_to, "lim": int(limit)},
        )
    ).all()
    return [int(r[0]) for r in rows]


async def load_order_head(session: AsyncSession, order_id: int) -> Optional[Dict[str, object]]:
    """
    读取 orders 的最小头信息（service 只依赖 platform/shop_id/ext_order_no）。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT id, platform, shop_id, ext_order_no
                  FROM orders
                 WHERE id = :oid
                 LIMIT 1
                """
            ),
            {"oid": int(order_id)},
        )
    ).mappings().first()
    return dict(row) if row else None


async def load_items(session: AsyncSession, order_id: int) -> Dict[int, Dict[str, object]]:
    """
    读取 order_items（按 item_id 聚合成 map）。

    返回结构：
      {
        item_id: {
          "qty_ordered": int,
          "sku_id": str,
          "title": str,
        }
      }
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT item_id, qty, sku_id, title
                  FROM order_items
                 WHERE order_id = :oid
                """
            ),
            {"oid": int(order_id)},
        )
    ).mappings().all()

    out: Dict[int, Dict[str, object]] = {}
    for r in rows:
        iid = int(r["item_id"])
        out[iid] = {
            "qty_ordered": int(r.get("qty") or 0),
            "sku_id": str(r.get("sku_id") or ""),
            "title": str(r.get("title") or ""),
        }
    return out


async def load_shipped(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Dict[int, int]:
    """
    shipped 来自 stock_ledger（ref=ORD:PLAT:SHOP:ext_no, delta<0）按 item_id 聚合。

    约定：
    - 出库 delta 为负；shipped_qty = -SUM(delta) where delta<0
    - 不强绑 reason（避免历史/演进导致 reason 名称变化）
    """
    ref = f"ORD:{str(platform).upper()}:{str(shop_id)}:{str(ext_order_no)}"
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  item_id,
                  SUM(-delta) AS shipped_qty
                FROM stock_ledger
                WHERE ref = :ref
                  AND delta < 0
                GROUP BY item_id
                """
            ),
            {"ref": ref},
        )
    ).mappings().all()

    result: Dict[int, int] = {}
    for r in rows:
        result[int(r["item_id"])] = int(r.get("shipped_qty") or 0)
    return result


async def load_returned(session: AsyncSession, order_id: int) -> Dict[int, int]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.item_id,
                        SUM(COALESCE(rl.qty_base, 0)) AS returned_qty
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
