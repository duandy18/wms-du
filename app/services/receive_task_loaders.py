# app/services/receive_task_loaders.py
from __future__ import annotations


from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase_order import PurchaseOrder


async def load_po(session: AsyncSession, po_id: int) -> PurchaseOrder:
    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.id == po_id)
    )
    res = await session.execute(stmt)
    po = res.scalars().first()
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")
    if po.lines:
        po.lines.sort(key=lambda line: (line.line_no, line.id))
    return po


async def load_order_item_qty_map(session: AsyncSession, order_id: int) -> dict[int, int]:
    rows = await session.execute(
        text(
            """
            SELECT item_id, COALESCE(qty, 0) AS qty
              FROM order_items
             WHERE order_id = :oid
            """
        ),
        {"oid": order_id},
    )
    result: dict[int, int] = {}
    for item_id, qty in rows:
        result[int(item_id)] = int(qty or 0)
    return result


async def load_order_returned_qty_map(session: AsyncSession, order_id: int) -> dict[int, int]:
    rows = await session.execute(
        text(
            """
            SELECT
                rtl.item_id,
                SUM(
                    COALESCE(
                        CASE
                            WHEN rt.status = 'COMMITTED' THEN rtl.committed_qty
                            ELSE COALESCE(rtl.expected_qty, rtl.scanned_qty)
                        END,
                        0
                    )
                ) AS returned_qty
              FROM receive_task_lines AS rtl
              JOIN receive_tasks AS rt
                ON rt.id = rtl.task_id
             WHERE rt.source_type = 'ORDER'
               AND rt.source_id = :oid
             GROUP BY rtl.item_id
            """
        ),
        {"oid": order_id},
    )
    result: dict[int, int] = {}
    for item_id, qty in rows:
        result[int(item_id)] = int(qty or 0)
    return result


async def load_order_shipped_qty_map(session: AsyncSession, order_id: int) -> dict[int, int]:
    head_row = (
        await session.execute(
            text(
                """
                SELECT platform, shop_id, ext_order_no
                  FROM orders
                 WHERE id = :oid
                 LIMIT 1
                """
            ),
            {"oid": order_id},
        )
    ).first()
    if not head_row:
        return {}

    platform, shop_id, ext_order_no = head_row
    plat = str(platform or "").upper()
    shop = str(shop_id or "")
    ext_no = str(ext_order_no or "")
    order_ref = f"ORD:{plat}:{shop}:{ext_no}"

    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        item_id,
                        SUM(CASE WHEN delta < 0 THEN -delta ELSE 0 END) AS shipped_qty
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

    result: dict[int, int] = {}
    for r in rows:
        result[int(r["item_id"])] = int(r.get("shipped_qty") or 0)
    return result


async def load_item_policy_map(
    session: AsyncSession, item_ids: list[int]
) -> dict[int, dict[str, object]]:
    """
    加载 item 的有效期策略与保质期参数（用于 commit 校验）：
    - has_shelf_life
    - shelf_life_value/unit（用于推算到期的参数）
    - name（用于报错）
    """
    if not item_ids:
        return {}

    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, name, has_shelf_life, shelf_life_value, shelf_life_unit
                      FROM items
                     WHERE id = ANY(:ids)
                    """
                ),
                {"ids": item_ids},
            )
        )
        .mappings()
        .all()
    )

    out: dict[int, dict[str, object]] = {}
    for r in rows:
        iid = int(r["id"])
        out[iid] = {
            "name": r.get("name"),
            "has_shelf_life": bool(r.get("has_shelf_life") or False),
            "shelf_life_value": r.get("shelf_life_value"),
            "shelf_life_unit": r.get("shelf_life_unit"),
        }
    return out
