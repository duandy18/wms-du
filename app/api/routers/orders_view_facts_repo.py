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


async def load_platform_items(session: AsyncSession, *, order_id: int) -> List[Dict[str, Any]]:
    """
    平台镜像行：从 order_items 读取平台侧可理解字段。
    - sku <- sku_id
    - 价格类字段 Decimal -> float（仅用于展示）
    - extras 为 JSONB（dict|None）
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      item_id,
                      sku_id,
                      title,
                      qty,
                      price,
                      discount,
                      amount,
                      extras
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

    def _f(v: object) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return None

    out: List[Dict[str, Any]] = []
    for r in rows:
        extras = r.get("extras")
        out.append(
            {
                "item_id": int(r["item_id"]) if r.get("item_id") is not None else None,
                "sku": str(r["sku_id"]) if r.get("sku_id") is not None else None,
                "title": str(r["title"]) if r.get("title") is not None else None,
                "qty": int(r["qty"]) if r.get("qty") is not None else 0,
                "spec": None,
                "price": _f(r.get("price")),
                "discount": _f(r.get("discount")),
                "amount": _f(r.get("amount")),
                "extras": dict(extras) if isinstance(extras, dict) else (extras if extras is None else dict(extras)),
            }
        )
    return out


async def load_order_address(session: AsyncSession, *, order_id: int) -> Optional[Dict[str, Any]]:
    """
    地址存在 order_address 表。这里用 SELECT * 避免依赖具体列名导致 SQL 失败。
    只挑镜像需要的字段输出。
    """
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
    """
    facts：订单镜像的“数量事实”（只读、无履约语义）。
    只输出 qty_ordered，用于详情页展示“下单数量”。
    """
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
