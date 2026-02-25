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
    """
    Phase 4E 测试造数：
    - 主事实：lots + stocks_lot（lot-world）
    - 禁止写 legacy batches + stocks（避免双余额源 / 口径回退）

    code 语义：
    - 作为 lot_code（SUPPLIER）展示码
    """
    wh = await _resolve_wh_by_loc(session, loc)
    expiry = date.today() + timedelta(days=days)

    # --- lot-world：确保 lots 存在（SUPPLIER 要求 lot_code 非空，source_receipt/source_line 必须为 NULL） ---
    lot_row = (
        await session.execute(
            SA(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
                    production_date,
                    expiry_date,
                    expiry_source
                )
                VALUES (:w, :i, 'SUPPLIER', :code, CURRENT_DATE, :exp, 'EXPLICIT')
                ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
                WHERE lot_code_source = 'SUPPLIER'
                DO UPDATE SET expiry_date = EXCLUDED.expiry_date
                RETURNING id
                """
            ),
            {"w": int(wh), "i": int(item), "code": str(code), "exp": expiry},
        )
    ).first()

    lot_id: Optional[int] = int(lot_row[0]) if lot_row else None
    if lot_id is None:
        row2 = (
            await session.execute(
                SA(
                    """
                    SELECT id
                      FROM lots
                     WHERE warehouse_id = :w
                       AND item_id      = :i
                       AND lot_code_source = 'SUPPLIER'
                       AND lot_code     = :code
                     LIMIT 1
                    """
                ),
                {"w": int(wh), "i": int(item), "code": str(code)},
            )
        ).first()
        lot_id = int(row2[0]) if row2 else None

    if lot_id is None:
        raise ValueError(f"failed to ensure lot for wh={wh}, item={item}, code={code}")

    await session.execute(
        SA(
            """
            INSERT INTO stocks_lot(item_id, warehouse_id, lot_id, qty)
            VALUES (:i, :w, :lot, :q)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot
            DO UPDATE SET qty = EXCLUDED.qty
            """
        ),
        {"i": int(item), "w": int(wh), "lot": int(lot_id), "q": int(qty)},
    )


async def seed_many(session: AsyncSession, entries: Iterable[Tuple[int, int, str, int, int]]) -> None:
    for item, loc, code, qty, days in entries:
        await seed_batch_slot(session, item=item, loc=loc, code=code, qty=qty, days=days)


async def sum_on_hand(session: AsyncSession, *, item: int, loc: int) -> int:
    """
    Phase 4D：测试口径以 lot-world 为准（stocks_lot）。
    """
    wh = await _resolve_wh_by_loc(session, loc)
    row = await session.execute(
        SA("SELECT COALESCE(SUM(qty),0) FROM stocks_lot WHERE item_id=:i AND warehouse_id=:w"),
        {"i": int(item), "w": int(wh)},
    )
    return int(row.scalar_one() or 0)


async def available(session: AsyncSession, *, item: int, loc: int) -> int:
    """
    测试口径：当前可售与在库一致（以 stocks_lot 为准）。
    """
    return await sum_on_hand(session, item=item, loc=loc)


async def qty_by_code(session: AsyncSession, *, item: int, loc: int, code: str) -> int:
    """
    Phase 4D：按 lot_code 汇总 qty（stocks_lot + lots）。
    """
    wh = await _resolve_wh_by_loc(session, loc)
    row = await session.execute(
        SA(
            """
            SELECT COALESCE(SUM(s.qty), 0)
              FROM stocks_lot s
              LEFT JOIN lots lo ON lo.id = s.lot_id
             WHERE s.item_id = :i
               AND s.warehouse_id = :w
               AND lo.lot_code = :code
            """
        ),
        {"i": int(item), "w": int(wh), "code": str(code)},
    )
    return int(row.scalar_one() or 0)


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
