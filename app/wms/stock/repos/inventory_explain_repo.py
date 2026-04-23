from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _norm_text(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


async def resolve_inventory_explain_anchor(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int | None,
    lot_code: str | None,
) -> dict[str, Any] | None:
    cond = [
        "s.item_id = :item_id",
        "s.warehouse_id = :warehouse_id",
        "s.qty <> 0",
    ]
    params: dict[str, Any] = {
        "item_id": int(item_id),
        "warehouse_id": int(warehouse_id),
    }

    if lot_id is not None:
        cond.append("s.lot_id = :lot_id")
        params["lot_id"] = int(lot_id)
    else:
        norm_lot_code = _norm_text(lot_code)
        if norm_lot_code is None:
            cond.append("l.lot_code IS NULL")
        else:
            cond.append("l.lot_code = :lot_code")
            params["lot_code"] = norm_lot_code

    sql = text(
        f"""
        SELECT
            s.item_id,
            i.name AS item_name,
            s.warehouse_id,
            w.name AS warehouse_name,
            s.lot_id,
            l.lot_code,
            s.qty AS current_qty,
            iu.id AS base_item_uom_id,
            COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS base_uom_name
        FROM stocks_lot AS s
        JOIN items AS i
          ON i.id = s.item_id
        JOIN warehouses AS w
          ON w.id = s.warehouse_id
        LEFT JOIN lots AS l
          ON l.id = s.lot_id
        LEFT JOIN item_uoms AS iu
          ON iu.item_id = s.item_id
         AND iu.is_base IS TRUE
        WHERE {" AND ".join(cond)}
        ORDER BY s.id ASC
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    if not rows:
        return None
    if len(rows) > 1:
        raise RuntimeError("ambiguous_inventory_explain_anchor")
    return dict(rows[0])


async def count_inventory_explain_ledger_rows(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
) -> int:
    sql = text(
        """
        SELECT COUNT(*)::int AS total
        FROM stock_ledger
        WHERE item_id = :item_id
          AND warehouse_id = :warehouse_id
          AND lot_id = :lot_id
        """
    )
    row = (await session.execute(
        sql,
        {
            "item_id": int(item_id),
            "warehouse_id": int(warehouse_id),
            "lot_id": int(lot_id),
        },
    )).mappings().first()
    return int((row or {}).get("total") or 0)


async def query_inventory_explain_ledger_rows(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
    limit: int,
) -> list[dict[str, Any]]:
    sql = text(
        """
        WITH picked AS (
            SELECT
                sl.id,
                sl.occurred_at,
                sl.created_at,
                sl.reason,
                sl.reason_canon,
                sl.sub_reason,
                sl.ref,
                sl.ref_line,
                sl.delta,
                sl.after_qty,
                sl.trace_id,
                sl.item_id,
                i.name AS item_name,
                sl.warehouse_id,
                sl.lot_id,
                l.lot_code,
                iu.id AS base_item_uom_id,
                COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS base_uom_name
            FROM stock_ledger AS sl
            JOIN items AS i
              ON i.id = sl.item_id
            LEFT JOIN lots AS l
              ON l.id = sl.lot_id
            LEFT JOIN item_uoms AS iu
              ON iu.item_id = sl.item_id
             AND iu.is_base IS TRUE
            WHERE sl.item_id = :item_id
              AND sl.warehouse_id = :warehouse_id
              AND sl.lot_id = :lot_id
            ORDER BY sl.occurred_at DESC, sl.id DESC
            LIMIT :limit
        )
        SELECT *
        FROM picked
        ORDER BY occurred_at ASC, id ASC
        """
    )
    rows = (await session.execute(
        sql,
        {
            "item_id": int(item_id),
            "warehouse_id": int(warehouse_id),
            "lot_id": int(lot_id),
            "limit": int(limit),
        },
    )).mappings().all()
    return [dict(r) for r in rows]


async def query_inventory_explain_latest_after_qty(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
) -> int | None:
    sql = text(
        """
        SELECT after_qty
        FROM stock_ledger
        WHERE item_id = :item_id
          AND warehouse_id = :warehouse_id
          AND lot_id = :lot_id
        ORDER BY occurred_at DESC, id DESC
        LIMIT 1
        """
    )
    row = (await session.execute(
        sql,
        {
            "item_id": int(item_id),
            "warehouse_id": int(warehouse_id),
            "lot_id": int(lot_id),
        },
    )).first()
    if row is None:
        return None
    return int(row[0])
