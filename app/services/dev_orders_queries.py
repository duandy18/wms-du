# app/services/dev_orders_queries.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_ref_helper import make_order_ref


async def get_order_head(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Optional[Mapping[str, Any]]:
    plat = platform.upper().strip()
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        id,
                        platform,
                        shop_id,
                        ext_order_no,
                        status,
                        trace_id,
                        created_at,
                        updated_at,
                        warehouse_id,
                        order_amount,
                        pay_amount
                      FROM orders
                     WHERE platform = :p
                       AND shop_id  = :s
                       AND ext_order_no = :o
                     LIMIT 1
                    """
                ),
                {"p": plat, "s": shop_id, "o": ext_order_no},
            )
        )
        .mappings()
        .first()
    )
    return row


async def get_order_facts(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    ext_order_no: str,
) -> Tuple[Mapping[str, Any], List[Dict[str, Any]]]:
    """
    返回：
      - 订单头（orders 表的一行）
      - items facts 列表：每个元素包含
          item_id / sku_id / title /
          qty_ordered / qty_shipped / qty_returned / remaining_refundable

    口径约束：
      - qty_shipped 只统计“真正发货”的台账：
          reason LIKE 'SHIP%' OR reason = 'OUTBOUND_SHIP'
        （即 SHIP / SHIPMENT / SHIP_OUT / OUTBOUND_SHIP 等）
      - 拣货（PICK）、退货出库（RETURN_OUT）、调整类负数不计入 shipped。
    """
    head = await get_order_head(
        session, platform=platform, shop_id=shop_id, ext_order_no=ext_order_no
    )
    if head is None:
        raise ValueError(
            f"order not found: platform={platform.upper()}, shop_id={shop_id}, ext_order_no={ext_order_no}"
        )

    order_id = int(head["id"])
    plat = str(head["platform"]).upper()
    s_id = str(head["shop_id"])
    ext_no = str(head["ext_order_no"])
    order_ref = make_order_ref(plat, s_id, ext_no)

    # 1) 订单行基础数据
    rows_items = (
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

    if not rows_items:
        return head, []

    ordered_map: Dict[int, Dict[str, Any]] = {}
    for r in rows_items:
        item_id = int(r["item_id"])
        ordered_map[item_id] = {
            "item_id": item_id,
            "sku_id": r.get("sku_id"),
            "title": r.get("title"),
            "qty_ordered": int(r.get("qty") or 0),
        }

    # 2) shipped：只认“发货类”台账
    rows_shipped = (
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
                       AND (
                             reason ILIKE 'SHIP%%'
                          OR reason = 'OUTBOUND_SHIP'
                       )
                     GROUP BY item_id
                    """
                ),
                {"ref": order_ref},
            )
        )
        .mappings()
        .all()
    )

    shipped_map: Dict[int, int] = {}
    for r in rows_shipped:
        item_id = int(r["item_id"])
        shipped_map[item_id] = int(r.get("shipped_qty") or 0)

    # 3) returned：RMA 收货任务
    rows_returned = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rtl.item_id,
                        SUM(COALESCE(rtl.committed_qty, 0)) AS returned_qty
                      FROM receive_task_lines AS rtl
                      JOIN receive_tasks AS rt
                        ON rt.id = rtl.task_id
                     WHERE rt.source_type = 'ORDER'
                       AND rt.source_id = :oid
                       AND rt.status = 'COMMITTED'
                     GROUP BY rtl.item_id
                    """
                ),
                {"oid": order_id},
            )
        )
        .mappings()
        .all()
    )

    returned_map: Dict[int, int] = {}
    for r in rows_returned:
        item_id = int(r["item_id"])
        returned_map[item_id] = int(r.get("returned_qty") or 0)

    # 4) 汇总 per item
    facts: List[Dict[str, Any]] = []
    for item_id, base in ordered_map.items():
        ordered_qty = int(base["qty_ordered"])
        shipped_qty = int(shipped_map.get(item_id, 0))
        returned_qty = int(returned_map.get(item_id, 0))
        remaining = max(min(ordered_qty, shipped_qty) - returned_qty, 0)

        facts.append(
            {
                "item_id": item_id,
                "sku_id": base["sku_id"],
                "title": base["title"],
                "qty_ordered": ordered_qty,
                "qty_shipped": shipped_qty,
                "qty_returned": returned_qty,
                "qty_remaining_refundable": remaining,
            }
        )

    return head, facts


async def list_orders_summary(
    session: AsyncSession,
    *,
    platform: Optional[str] = None,
    shop_id: Optional[str] = None,
    status: Optional[str] = None,
    time_from: Optional[datetime] = None,
    time_to: Optional[datetime] = None,
    limit: int = 100,
) -> List[Mapping[str, Any]]:
    clauses: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    if platform:
        clauses.append("platform = :p")
        params["p"] = platform.upper()
    if shop_id:
        clauses.append("shop_id = :s")
        params["s"] = shop_id
    if status:
        clauses.append("status = :st")
        params["st"] = status
    if time_from:
        clauses.append("created_at >= :from_ts")
        params["from_ts"] = time_from
    if time_to:
        clauses.append("created_at <= :to_ts")
        params["to_ts"] = time_to

    where_sql = ""
    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    rows = (
        (
            await session.execute(
                text(
                    f"""
                    SELECT
                        id,
                        platform,
                        shop_id,
                        ext_order_no,
                        status,
                        created_at,
                        updated_at,
                        warehouse_id,
                        order_amount,
                        pay_amount
                      FROM orders
                      {where_sql}
                     ORDER BY created_at DESC, id DESC
                     LIMIT :limit
                    """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    return rows
