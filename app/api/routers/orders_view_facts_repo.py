# app/api/routers/orders_view_facts_repo.py
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def load_order_head_by_keys(
    session: AsyncSession, *, platform: str, shop_id: str, ext_order_no: str
) -> Mapping[str, Any]:
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
                      created_at,
                      updated_at,
                      order_amount,
                      pay_amount,
                      buyer_name,
                      buyer_phone
                    FROM orders
                    WHERE platform = :p
                      AND shop_id = :s
                      AND ext_order_no = :e
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"p": platform.upper(), "s": shop_id, "e": ext_order_no},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"order not found: {platform}/{shop_id}/{ext_order_no}")
    return row


async def load_order_head_by_id(
    session: AsyncSession, *, order_id: int
) -> Mapping[str, Any]:
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
                      created_at,
                      updated_at,
                      order_amount,
                      pay_amount,
                      buyer_name,
                      buyer_phone
                    FROM orders
                    WHERE id = :oid
                    LIMIT 1
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise ValueError(f"order not found: id={order_id}")
    return row


async def load_order_head_raw_by_id(session: AsyncSession, *, order_id: int) -> Optional[Dict[str, Any]]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT *
                      FROM orders
                     WHERE id = :oid
                     LIMIT 1
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return dict(row)


async def load_order_items_raw(session: AsyncSession, *, order_id: int) -> List[Dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT *
                      FROM order_items
                     WHERE order_id = :oid
                     ORDER BY id ASC
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


async def load_order_address_raw(session: AsyncSession, *, order_id: int) -> Optional[Dict[str, Any]]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT *
                      FROM order_address
                     WHERE order_id = :oid
                     ORDER BY id DESC
                     LIMIT 1
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return dict(row)


async def load_platform_items(session: AsyncSession, *, order_id: int) -> List[Dict[str, Any]]:
    """
    平台镜像行：
    - 直接读取 platform_order_lines
    - 不聚合
    - 不读取 order_items
    - 完全还原平台原始单行
    """
    head = (
        (
            await session.execute(
                text(
                    """
                    SELECT platform, shop_id, ext_order_no
                    FROM orders
                    WHERE id = :oid
                    LIMIT 1
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .first()
    )

    if not head:
        return []

    platform = str(head["platform"])
    shop_id = str(head["shop_id"])
    ext = str(head["ext_order_no"])

    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      line_no,
                      filled_code,
                      title,
                      spec,
                      qty,
                      raw_payload
                    FROM platform_order_lines
                    WHERE platform = :p
                      AND shop_id = :s
                      AND ext_order_no = :e
                    ORDER BY line_no ASC
                    """
                ),
                {"p": platform, "s": shop_id, "e": ext},
            )
        )
        .mappings()
        .all()
    )

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "item_id": None,
                "sku": r.get("filled_code"),
                "title": r.get("title"),
                "qty": int(r.get("qty") or 0),
                "spec": r.get("spec"),
                "price": None,
                "discount": None,
                "amount": None,
                "extras": r.get("raw_payload"),
            }
        )

    return out


async def load_order_address(session: AsyncSession, *, order_id: int) -> Optional[Dict[str, Any]]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT *
                    FROM order_address
                    WHERE order_id = :oid
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None

    def pick(*keys: str) -> Optional[str]:
        for k in keys:
            v = row.get(k)
            if v is None:
                continue
            s = str(v).strip()
            if s:
                return s
        return None

    return {
        "receiver_name": pick("receiver_name", "consignee", "name"),
        "receiver_phone": pick("receiver_phone", "phone", "mobile", "tel"),
        "province": pick("province", "prov", "state"),
        "city": pick("city"),
        "district": pick("district", "county", "area"),
        "detail": pick("detail", "address", "detail_address", "street"),
        "zipcode": pick("zipcode", "zip"),
    }


async def load_order_facts_full(
    session: AsyncSession, *, order_id: int
) -> Dict[str, Any]:
    """
    正式 orders facts 合同（完整版）。

    口径：
    - qty_ordered   来自 order_items.qty
    - qty_shipped   来自 stock_ledger(ref=ORD:PLAT:SHOP:EXT, delta<0)
    - qty_returned  来自 inbound_receipts(source_type='ORDER', status='CONFIRMED')
    - qty_remaining_refundable = max(min(qty_ordered, qty_shipped) - qty_returned, 0)
    """
    head = await load_order_head_by_id(session, order_id=order_id)

    platform = str(head["platform"]).upper()
    shop_id = str(head["shop_id"])
    ext_order_no = str(head["ext_order_no"])
    order_ref = f"ORD:{platform}:{shop_id}:{ext_order_no}"

    item_rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT item_id, qty, sku_id, title
                    FROM order_items
                    WHERE order_id = :oid
                    ORDER BY id ASC
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .all()
    )

    shipped_rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      item_id,
                      SUM(-delta) AS qty_shipped
                    FROM stock_ledger
                    WHERE ref = :ref
                      AND delta < 0
                    GROUP BY item_id
                    """
                ),
                {"ref": order_ref},
            )
        )
        .mappings()
        .all()
    )

    returned_rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      rl.item_id,
                      SUM(COALESCE(rl.qty_base, 0)) AS qty_returned
                    FROM inbound_receipt_lines AS rl
                    JOIN inbound_receipts AS r
                      ON r.id = rl.receipt_id
                    WHERE r.source_type = 'ORDER'
                      AND r.source_id = :oid
                      AND r.status = 'CONFIRMED'
                    GROUP BY rl.item_id
                    """
                ),
                {"oid": int(order_id)},
            )
        )
        .mappings()
        .all()
    )

    shipped_map: Dict[int, int] = {
        int(r["item_id"]): int(r.get("qty_shipped") or 0) for r in shipped_rows
    }
    returned_map: Dict[int, int] = {
        int(r["item_id"]): int(r.get("qty_returned") or 0) for r in returned_rows
    }

    items_map: Dict[int, Dict[str, Any]] = {}
    items: List[Dict[str, Any]] = []
    issues: List[str] = []

    for r in item_rows:
        item_id = int(r["item_id"])
        qty_ordered = int(r.get("qty") or 0)
        qty_shipped = int(shipped_map.get(item_id, 0))
        qty_returned = int(returned_map.get(item_id, 0))
        qty_remaining_refundable = max(min(qty_ordered, qty_shipped) - qty_returned, 0)

        if qty_shipped > qty_ordered:
            issues.append(
                f"item_id={item_id} shipped({qty_shipped}) > ordered({qty_ordered})"
            )
        if qty_returned > qty_shipped:
            issues.append(
                f"item_id={item_id} returned({qty_returned}) > shipped({qty_shipped})"
            )

        row = {
            "item_id": item_id,
            "sku_id": str(r["sku_id"]) if r.get("sku_id") is not None else None,
            "title": str(r["title"]) if r.get("title") is not None else None,
            "qty_ordered": qty_ordered,
            "qty_shipped": qty_shipped,
            "qty_returned": qty_returned,
            "qty_remaining_refundable": qty_remaining_refundable,
        }
        items_map[item_id] = row
        items.append(row)

    for item_id in shipped_map.keys():
        if item_id not in items_map:
            issues.append(
                f"ledger has shipped item_id={item_id}, but order_items has no row for it"
            )

    for item_id in returned_map.keys():
        if item_id not in items_map:
            issues.append(
                f"RMA has returned item_id={item_id}, but order_items has no row for it"
            )

    return {
        "order_id": int(head["id"]),
        "platform": platform,
        "shop_id": shop_id,
        "ext_order_no": ext_order_no,
        "issues": issues,
        "items": items,
    }
