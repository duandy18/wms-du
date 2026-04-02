# app/wms/inventory/services/lots.py
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_lot_code(code: str | None) -> tuple[str, str]:
    """
    Normalize supplier lot_code to prevent drift.

    Returns:
        (code_raw, code_key)

    Rules:
        - code_raw: stripped original input (kept for display)
        - code_key: upper(trim(code_raw)) used for uniqueness / lookups
    """
    s = (str(code) if code is not None else "").strip()
    if not s:
        raise ValueError("lot_code empty")
    return s, s.upper()


def _pair_or_null(a: Optional[int], b: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    """
    INTERNAL lot source fields rule:
    - both NULL, or both NOT NULL.
    """
    if a is None and b is None:
        return None, None
    if a is not None and b is not None:
        return int(a), int(b)
    raise ValueError("internal_source_receipt_line_pair_required")


async def ensure_internal_lot_singleton(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    source_receipt_id: Optional[int] = None,
    source_line_no: Optional[int] = None,
) -> int:
    """
    INTERNAL lot singleton (warehouse_id, item_id):
    - lot_code_source='INTERNAL'
    - lot_code IS NULL (enforced by ck_lots_lot_code_by_source)
    - UNIQUE (warehouse_id,item_id) WHERE INTERNAL & lot_code IS NULL

    source_receipt_id/source_line_no are optional provenance fields:
    - both NULL, or both NOT NULL (enforced by ck_lots_internal_source_receipt_line_pair)
    """
    rid, rln = _pair_or_null(source_receipt_id, source_line_no)

    row0 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'INTERNAL'
               AND lot_code IS NULL
             ORDER BY id ASC
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id)},
    )
    got0 = row0.scalar_one_or_none()
    if got0 is not None:
        return int(got0)

    row = await session.execute(
        text(
            """
            INSERT INTO lots(
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                lot_code_key,
                source_receipt_id,
                source_line_no,
                -- required snapshots (NOT NULL)
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot,
                -- optional snapshots (nullable)
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot
            )
            SELECT
                :w,
                :i,
                'INTERNAL',
                NULL,
                NULL,
                :rid,
                :rln,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled,
                it.shelf_life_value,
                it.shelf_life_unit
              FROM items it
             WHERE it.id = :i
            ON CONFLICT DO NOTHING
            RETURNING id
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "rid": rid, "rln": rln},
    )
    got = row.scalar_one_or_none()
    if got is not None:
        return int(got)

    row2 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'INTERNAL'
               AND lot_code IS NULL
             ORDER BY id ASC
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id)},
    )
    got2 = row2.scalar_one_or_none()
    if got2 is None:
        raise RuntimeError("ensure_internal_lot_singleton failed to materialize INTERNAL lot row")
    return int(got2)


async def ensure_lot_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    lot_code: str,
    production_date,
    expiry_date,
) -> int:
    """
    SUPPLIER lot 唯一入口。

    注意：supplier 唯一性是 partial unique index：
      uq_lots_wh_item_lot_code_key (warehouse_id,item_id,lot_code_key) WHERE lot_code IS NOT NULL
    因此 ON CONFLICT 必须携带相同 WHERE 子句，否则 PG 会报 InvalidColumnReference。
    """
    _ = production_date
    _ = expiry_date

    code_raw, code_key = normalize_lot_code(lot_code)

    row = await session.execute(
        text(
            """
            INSERT INTO lots(
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                lot_code_key,
                source_receipt_id,
                source_line_no,
                -- required snapshots (NOT NULL)
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot,
                -- optional snapshots (nullable)
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot
            )
            SELECT
                :w,
                :i,
                'SUPPLIER',
                :code_raw,
                :code_key,
                NULL,
                NULL,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled,
                it.shelf_life_value,
                it.shelf_life_unit
              FROM items it
             WHERE it.id = :i
            ON CONFLICT (warehouse_id, item_id, lot_code_key)
            WHERE lot_code IS NOT NULL
            DO NOTHING
            RETURNING id
            """
        ),
        {
            "w": int(warehouse_id),
            "i": int(item_id),
            "code_raw": code_raw,
            "code_key": code_key,
        },
    )
    got = row.scalar_one_or_none()
    if got is not None:
        return int(got)

    row2 = await session.execute(
        text(
            """
            SELECT id
              FROM lots
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_code_source = 'SUPPLIER'
               AND lot_code_key = :code_key
             LIMIT 1
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "code_key": code_key},
    )
    got2 = row2.scalar_one_or_none()
    if got2 is None:
        raise RuntimeError("ensure_lot_full failed to materialize lot row")
    return int(got2)


async def ensure_batch_full(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    production_date,
    expiry_date,
) -> int:
    return await ensure_lot_full(
        session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        lot_code=batch_code,
        production_date=production_date,
        expiry_date=expiry_date,
    )


__all__ = [
    "normalize_lot_code",
    "ensure_internal_lot_singleton",
    "ensure_lot_full",
    "ensure_batch_full",
]
