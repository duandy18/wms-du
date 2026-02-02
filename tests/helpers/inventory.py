# tests/helpers/inventory.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

UTC = timezone.utc

__all__ = [
    "_has_table",
    "_columns_of",
    "ensure_wh_loc_item",
    "seed_batch_slot",
    "seed_many",
    "qty_by_code",
    "sum_on_hand",
    "sum_reserved_active",
    "available",
    "insert_snapshot",
]


async def _has_table(session: AsyncSession, tbl: str) -> bool:
    row = await session.execute(SA("SELECT to_regclass(:q) IS NOT NULL"), {"q": f"public.{tbl}"})
    return bool(row.scalar_one())


async def _columns_of(session: AsyncSession, tbl: str) -> List[str]:
    if not await _has_table(session, tbl):
        return []
    rows = await session.execute(
        SA(
            """
            SELECT column_name
              FROM information_schema.columns
             WHERE table_schema='public' AND table_name=:t
             ORDER BY ordinal_position
        """
        ),
        {"t": tbl},
    )
    return [r[0] for r in rows.fetchall()]


async def ensure_wh_loc_item(
    session: AsyncSession,
    *,
    wh: int,
    loc: int,
    item: int,
    code: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    await session.execute(
        SA("INSERT INTO warehouses (id, name) VALUES (:w, 'WH') ON CONFLICT (id) DO NOTHING"),
        {"w": wh},
    )
    await session.execute(
        SA(
            "INSERT INTO locations (id, warehouse_id, code, name) "
            "VALUES (:l, :w, :code, :name) ON CONFLICT (id) DO NOTHING"
        ),
        {"l": loc, "w": wh, "code": code or f"LOC-{loc}", "name": name or code or f"LOC-{loc}"},
    )
    await session.execute(
        SA(
            "INSERT INTO items (id, sku, name) VALUES (:i, :s, :n) "
            "ON CONFLICT (id) DO UPDATE SET sku=EXCLUDED.sku, name=EXCLUDED.name"
        ),
        {"i": item, "s": f"SKU-{item}", "n": f"ITEM-{item}"},
    )


async def _resolve_wh_by_loc(session: AsyncSession, loc: int) -> int:
    row = await session.execute(
        SA("SELECT warehouse_id FROM locations WHERE id=:loc"),
        {"loc": loc},
    )
    wh = row.scalar_one_or_none()
    if wh is None:
        raise ValueError(f"no warehouse_id for location id={loc}")
    return int(wh)


async def seed_batch_slot(
    session: AsyncSession,
    *,
    item: int,
    loc: int,
    code: str,
    qty: int,
    days: int = 365,
) -> None:
    wh = await _resolve_wh_by_loc(session, loc)
    expiry = date.today() + timedelta(days=days)

    await session.execute(
        SA(
            """
            INSERT INTO batches (item_id, warehouse_id, batch_code, expiry_date)
            VALUES (:i, :w, :code, :exp)
            ON CONFLICT (item_id, warehouse_id, batch_code) DO NOTHING
            """
        ),
        {"i": item, "w": wh, "code": code, "exp": expiry},
    )

    await session.execute(
        SA(
            """
            INSERT INTO stocks (item_id, warehouse_id, batch_code, qty)
            VALUES (:i, :w, :code, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_item_wh_batch DO NOTHING
            """
        ),
        {"i": item, "w": wh, "code": code},
    )

    await session.execute(
        SA(
            """
            UPDATE stocks
               SET qty = :q
             WHERE item_id = :i
               AND warehouse_id = :w
               AND batch_code = :code
            """
        ),
        {"q": qty, "i": item, "w": wh, "code": code},
    )


async def seed_many(session: AsyncSession, entries: Iterable[Tuple[int, int, str, int, int]]) -> None:
    for item, loc, code, qty, days in entries:
        await seed_batch_slot(session, item=item, loc=loc, code=code, qty=qty, days=days)


async def sum_on_hand(session: AsyncSession, *, item: int, loc: int) -> int:
    wh = await _resolve_wh_by_loc(session, loc)
    row = await session.execute(
        SA("SELECT COALESCE(SUM(qty),0) FROM stocks WHERE item_id=:i AND warehouse_id=:w"),
        {"i": item, "w": wh},
    )
    return int(row.scalar_one() or 0)


async def sum_reserved_active(session: AsyncSession, *, item: int, loc: int) -> int:
    cols = await _columns_of(session, "reservations")
    if {"item_id", "location_id", "qty", "status"}.issubset(set(cols)):
        row = await session.execute(
            SA(
                "SELECT COALESCE(SUM(qty),0) FROM reservations "
                "WHERE item_id=:i AND location_id=:l AND status='ACTIVE'"
            ),
            {"i": item, "l": loc},
        )
        return int(row.scalar_one() or 0)
    return 0


async def available(session: AsyncSession, *, item: int, loc: int) -> int:
    return await sum_on_hand(session, item=item, loc=loc) - await sum_reserved_active(session, item=item, loc=loc)


async def qty_by_code(session: AsyncSession, *, item: int, loc: int, code: str) -> int:
    wh = await _resolve_wh_by_loc(session, loc)
    row = await session.execute(
        SA(
            """
            SELECT qty
              FROM stocks
             WHERE item_id = :i
               AND warehouse_id = :w
               AND batch_code = :code
             LIMIT 1
            """
        ),
        {"i": item, "w": wh, "code": code},
    )
    return int(row.scalar_one_or_none() or 0)


async def insert_snapshot(
    session: AsyncSession,
    *,
    ts: datetime,
    day: date,
    item: int,
    loc: int,
    on_hand: int,
    available: int,
) -> None:
    _ = ts
    wh = await _resolve_wh_by_loc(session, loc)

    await session.execute(
        SA(
            """
            INSERT INTO stock_snapshots (
                snapshot_date,
                warehouse_id,
                item_id,
                batch_code,
                qty,
                qty_available,
                qty_allocated
            )
            VALUES (:day, :w, :i, 'SNAP-TEST', :q, :av, 0)
            ON CONFLICT ON CONSTRAINT uq_stock_snapshot_grain_v2
            DO UPDATE SET
                qty           = stock_snapshots.qty + EXCLUDED.qty,
                qty_available = stock_snapshots.qty_available + EXCLUDED.qty_available
            """
        ),
        {"day": day, "w": wh, "i": item, "q": on_hand, "av": available},
    )
