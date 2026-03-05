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


# 🔥 关键修改：镜像层改为读取 platform_order_lines（原始平台单行）
async def load_platform_items(session: AsyncSession, *, order_id: int) -> List[Dict[str, Any]]:
    """
    平台镜像行：
    - 直接读取 platform_order_lines
    - 不聚合
    - 不读取 order_items
    - 完全还原平台原始单行
    """

    # 1️⃣ 通过 order_id 反查三件套
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

    # 2️⃣ 读取 platform_order_lines（最原始平台数据）
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


async def load_order_facts(session: AsyncSession, *, order_id: int) -> List[Dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      item_id,
                      sku_id,
                      title,
                      qty
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

    out: List[Dict[str, Any]] = []
    for r in rows:
        qty = int(r["qty"]) if r.get("qty") is not None else 0
        out.append(
            {
                "item_id": int(r["item_id"]) if r.get("item_id") is not None else 0,
                "sku_id": str(r["sku_id"]) if r.get("sku_id") is not None else None,
                "title": str(r["title"]) if r.get("title") is not None else None,
                "qty_ordered": qty,
            }
        )
    return out
