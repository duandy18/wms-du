# app/services/order_ingest_items_writer.py
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_utils import to_dec_str


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
            "oid": order_id,
            "item_id": it.get("item_id"),
            "sku_id": (it.get("sku_id") or "")[:128],
            "title": (it.get("title") or "")[:255],
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
