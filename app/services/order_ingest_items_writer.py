# app/services/order_ingest_items_writer.py
from __future__ import annotations

import json
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_utils import to_dec_str


def _norm_str(v: Any, *, max_len: int) -> Optional[str]:
    """
    统一字符串快照写入口径（非常重要）：
    - None / 空串 / 全空白 => 写 NULL（避免污染快照）
    - 其他 => strip 后截断
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s[: int(max_len)]


async def insert_order_items(
    session: AsyncSession,
    *,
    order_id: int,
    items: Sequence[Mapping[str, Any]],
    order_items_has_extras: bool,
) -> None:
    if not items:
        return

    if order_items_has_extras:
        sql_item = text(
            """
            INSERT INTO order_items (
                order_id,
                item_id,
                sku_id,
                title,
                qty,
                price,
                discount,
                amount,
                shipped_qty,
                returned_qty,
                extras
            )
            VALUES (
                :oid, :item_id, :sku_id, :title,
                :qty, :price, :disc, :amt,
                :shipped_qty, :returned_qty,
                CAST(:ex AS jsonb)
            )
            ON CONFLICT ON CONSTRAINT uq_order_items_ord_sku DO NOTHING
            """
        )
    else:
        sql_item = text(
            """
            INSERT INTO order_items (
                order_id,
                item_id,
                sku_id,
                title,
                qty,
                price,
                discount,
                amount,
                shipped_qty,
                returned_qty
            )
            VALUES (
                :oid, :item_id, :sku_id, :title,
                :qty, :price, :disc, :amt,
                :shipped_qty, :returned_qty
            )
            ON CONFLICT ON CONSTRAINT uq_order_items_ord_sku DO NOTHING
            """
        )

    for it in items:
        params = {
            "oid": int(order_id),
            "item_id": it.get("item_id"),
            # ✅ 写入层归一：空串=>NULL，避免污染快照/聚合
            "sku_id": _norm_str(it.get("sku_id"), max_len=128),
            "title": _norm_str(it.get("title"), max_len=255),
            "qty": int(it.get("qty") or 0),
            "price": to_dec_str(it.get("price")),
            "disc": to_dec_str(it.get("discount")),
            "amt": to_dec_str(it.get("amount")),
            "shipped_qty": 0,
            "returned_qty": 0,
        }
        if order_items_has_extras:
            params["ex"] = json.dumps(it.get("extras") or {}, ensure_ascii=False)
        await session.execute(sql_item, params)
