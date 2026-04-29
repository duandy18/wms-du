from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def _norm_text(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _build_inventory_where(
    *,
    q: str | None,
    item_id: int | None,
    warehouse_id: int | None,
    lot_code: str | None,
    near_expiry: bool | None,
) -> tuple[str, dict[str, Any]]:
    cond = ["s.qty <> 0"]
    params: dict[str, Any] = {}

    q_norm = _norm_text(q)
    lot_norm = _norm_text(lot_code)

    if q_norm is not None:
        cond.append("(i.name ILIKE :q OR i.sku ILIKE :q)")
        params["q"] = f"%{q_norm}%"

    if item_id is not None:
        cond.append("s.item_id = :item_id")
        params["item_id"] = int(item_id)

    if warehouse_id is not None:
        cond.append("s.warehouse_id = :warehouse_id")
        params["warehouse_id"] = int(warehouse_id)

    if lot_norm is not None:
        cond.append("l.lot_code = :lot_code")
        params["lot_code"] = lot_norm

    if near_expiry is True:
        cond.append(
            "l.expiry_date IS NOT NULL "
            "AND l.expiry_date >= CURRENT_DATE "
            "AND l.expiry_date <= CURRENT_DATE + 30"
        )

    return " AND ".join(cond), params


async def query_inventory_rows(
    session: AsyncSession,
    *,
    q: str | None,
    item_id: int | None,
    warehouse_id: int | None,
    lot_code: str | None,
    near_expiry: bool | None,
    offset: int,
    limit: int,
) -> tuple[int, list[dict[str, Any]]]:
    where_sql, params = _build_inventory_where(
        q=q,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=lot_code,
        near_expiry=near_expiry,
    )
    params["offset"] = int(offset)
    params["limit"] = int(limit)

    count_sql = text(
        f"""
        WITH base AS (
            SELECT
                s.item_id,
                s.warehouse_id,
                s.lot_id
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
            WHERE {where_sql}
        )
        SELECT COUNT(*)::int AS total
        FROM base
        """
    )
    total_row = (await session.execute(count_sql, params)).mappings().first()
    total = int((total_row or {}).get("total") or 0)

    list_sql = text(
        f"""
        SELECT
            s.item_id,
            i.name AS item_name,
            i.sku AS item_code,
            i.spec AS spec,
            b.name_cn AS brand,
            c.category_name AS category,
            s.warehouse_id,
            w.name AS warehouse_name,
            l.lot_code AS lot_code,
            l.production_date AS production_date,
            l.expiry_date AS expiry_date,
            s.qty,
            iu.id AS base_item_uom_id,
            COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS base_uom_name,
            (
                SELECT ib.barcode
                FROM item_barcodes AS ib
                WHERE ib.item_id = s.item_id
                  AND ib.active = TRUE
                ORDER BY ib.is_primary DESC, ib.id ASC
                LIMIT 1
            ) AS main_barcode
        FROM stocks_lot AS s
        JOIN items AS i
          ON i.id = s.item_id
        LEFT JOIN pms_brands AS b
          ON b.id = i.brand_id
        LEFT JOIN pms_business_categories AS c
          ON c.id = i.category_id
        JOIN warehouses AS w
          ON w.id = s.warehouse_id
        LEFT JOIN lots AS l
          ON l.id = s.lot_id
        LEFT JOIN item_uoms AS iu
          ON iu.item_id = s.item_id
         AND iu.is_base IS TRUE
        WHERE {where_sql}
        ORDER BY i.name ASC, s.item_id ASC, s.warehouse_id ASC, l.lot_code NULLS FIRST
        OFFSET :offset
        LIMIT :limit
        """
    )
    rows = (await session.execute(list_sql, params)).mappings().all()
    return total, [dict(r) for r in rows]


async def query_inventory_detail_rows(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int | None,
    lot_code: str | None,
) -> list[dict[str, Any]]:
    cond = [
        "s.item_id = :item_id",
        "s.qty <> 0",
    ]
    params: dict[str, Any] = {"item_id": int(item_id)}

    lot_norm = _norm_text(lot_code)
    if warehouse_id is not None:
        cond.append("s.warehouse_id = :warehouse_id")
        params["warehouse_id"] = int(warehouse_id)
    if lot_norm is not None:
        cond.append("l.lot_code = :lot_code")
        params["lot_code"] = lot_norm

    sql = text(
        f"""
        SELECT
            s.item_id,
            i.name AS item_name,
            iu.id AS base_item_uom_id,
            COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS base_uom_name,
            s.warehouse_id,
            w.name AS warehouse_name,
            l.lot_code AS lot_code,
            l.production_date AS production_date,
            l.expiry_date AS expiry_date,
            s.qty
        FROM stocks_lot AS s
        JOIN items AS i
          ON i.id = s.item_id
        LEFT JOIN pms_brands AS b
          ON b.id = i.brand_id
        LEFT JOIN pms_business_categories AS c
          ON c.id = i.category_id
        JOIN warehouses AS w
          ON w.id = s.warehouse_id
        LEFT JOIN lots AS l
          ON l.id = s.lot_id
        LEFT JOIN item_uoms AS iu
          ON iu.item_id = s.item_id
         AND iu.is_base IS TRUE
        WHERE {" AND ".join(cond)}
        ORDER BY s.warehouse_id ASC, l.lot_code NULLS FIRST
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


__all__ = [
    "query_inventory_rows",
    "query_inventory_detail_rows",
]
