# tests/helpers/inventory.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from tests.utils.ensure_minimal import ensure_item

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


def _wh_from_loc(loc: int) -> int:
    """
    Phase M-5+：locations 表已物理删除。

    历史测试 helper 里大量使用 ensure_wh_loc_item(..., loc=wh, ...) 这种“loc=wh”的写法。
    为了避免全量改调用点，又要保持终态一致（不复活 locations），这里统一将 loc 解释为 warehouse_id。
    """
    return int(loc)


def _norm_lot_key(code_raw: str) -> str:
    return str(code_raw).strip().lower()


async def ensure_wh_loc_item(
    session: AsyncSession,
    *,
    wh: int,
    loc: int,
    item: int,
    code: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    _ = loc
    _ = code
    _ = name

    await session.execute(
        SA("INSERT INTO warehouses (id, name) VALUES (:w, 'WH') ON CONFLICT (id) DO NOTHING"),
        {"w": int(wh)},
    )

    await ensure_item(session, id=int(item), sku=f"SKU-{item}", name=f"ITEM-{item}")


async def _ensure_supplier_lot(session: AsyncSession, *, wh: int, item: int, code: str) -> int:
    """
    Lot-World v2：SUPPLIER lot 幂等 upsert，唯一键使用 lot_code_key。
    """
    code_raw = str(code).strip()
    if not code_raw:
        raise ValueError("lot_code empty")

    code_key = _norm_lot_key(code_raw)

    row = (
        await session.execute(
            SA(
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
                    -- optional snapshots
                    item_shelf_life_value_snapshot,
                    item_shelf_life_unit_snapshot,
                    created_at
                )
                SELECT
                    :w,
                    it.id,
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
                    it.shelf_life_unit,
                    now()
                  FROM items it
                 WHERE it.id = :i
                ON CONFLICT (warehouse_id, item_id, lot_code_key)
                WHERE lot_code IS NOT NULL
                DO UPDATE SET lot_code = EXCLUDED.lot_code
                RETURNING id
                """
            ),
            {"w": int(wh), "i": int(item), "code_raw": code_raw, "code_key": code_key},
        )
    ).first()

    if not row:
        raise ValueError(f"failed to ensure SUPPLIER lot for wh={wh}, item={item}, code={code}")

    return int(row[0])


async def _ensure_internal_lot(session: AsyncSession, *, wh: int, item: int, ref: str) -> int:
    """
    INTERNAL 单例 lot（终态）：
    - lot_code_source='INTERNAL'
    - lot_code IS NULL
    - UNIQUE (warehouse_id,item_id) WHERE INTERNAL & lot_code IS NULL

    ref 参数仅保留调用点形态，不再用于 identity。
    """
    _ = ref

    r0 = await session.execute(
        SA(
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
        {"w": int(wh), "i": int(item)},
    )
    got0 = r0.scalar_one_or_none()
    if got0 is not None:
        return int(got0)

    await session.execute(
        SA(
            """
            INSERT INTO lots(
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
                lot_code_key,
                source_receipt_id,
                source_line_no,
                created_at,
                item_shelf_life_value_snapshot,
                item_shelf_life_unit_snapshot,
                item_lot_source_policy_snapshot,
                item_expiry_policy_snapshot,
                item_derivation_allowed_snapshot,
                item_uom_governance_enabled_snapshot
            )
            SELECT
                :w,
                it.id,
                'INTERNAL',
                NULL,
                NULL,
                NULL,
                NULL,
                now(),
                it.shelf_life_value,
                it.shelf_life_unit,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled
            FROM items it
            WHERE it.id = :i
            ON CONFLICT DO NOTHING
            """
        ),
        {"w": int(wh), "i": int(item)},
    )

    r1 = await session.execute(
        SA(
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
        {"w": int(wh), "i": int(item)},
    )
    got1 = r1.scalar_one_or_none()
    if got1 is None:
        raise ValueError("failed to ensure INTERNAL lot")
    return int(got1)


async def seed_batch_slot(
    session: AsyncSession,
    *,
    item: int,
    loc: int,
    code: str,
    qty: int,
    days: int = 365,
) -> None:
    wh = _wh_from_loc(loc)
    _ = date.today() + timedelta(days=days)  # lots 不再承载日期事实
    lot_id = await _ensure_supplier_lot(session, wh=int(wh), item=int(item), code=str(code))

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
    wh = _wh_from_loc(loc)
    row = await session.execute(
        SA("SELECT COALESCE(SUM(qty),0) FROM stocks_lot WHERE item_id=:i AND warehouse_id=:w"),
        {"i": int(item), "w": int(wh)},
    )
    return int(row.scalar_one() or 0)


async def available(session: AsyncSession, *, item: int, loc: int) -> int:
    return await sum_on_hand(session, item=item, loc=loc)


async def qty_by_code(session: AsyncSession, *, item: int, loc: int, code: str) -> int:
    wh = _wh_from_loc(loc)
    row = await session.execute(
        SA(
            """
            SELECT COALESCE(SUM(s.qty), 0)
              FROM stocks_lot s
              JOIN lots lo ON lo.id = s.lot_id
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
    wh = _wh_from_loc(loc)

    # 快照必须绑定真实 lot_id；这里用 INTERNAL 单例 lot 承载“无指定展示码”的快照场景
    lot_id = await _ensure_internal_lot(
        session,
        wh=int(wh),
        item=int(item),
        ref=f"UT-SNAP-INTERNAL-{int(datetime.now(UTC).timestamp())}",
    )

    await session.execute(
        SA(
            """
            INSERT INTO stock_snapshots (
                snapshot_date,
                warehouse_id,
                item_id,
                lot_id,
                qty,
                qty_available,
                qty_allocated
            )
            VALUES (:day, :w, :i, :lot, :q, :av, :al)
            ON CONFLICT ON CONSTRAINT uq_stock_snapshots_grain_lot
            DO UPDATE SET
                qty           = EXCLUDED.qty,
                qty_available = EXCLUDED.qty_available,
                qty_allocated = EXCLUDED.qty_allocated
            """
        ),
        {
            "day": day,
            "w": int(wh),
            "i": int(item),
            "lot": int(lot_id),
            "q": int(on_hand),
            "av": int(available),
            "al": int(on_hand) - int(available),
        },
    )
