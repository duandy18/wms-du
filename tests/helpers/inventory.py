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

    规则：
    - loc 参数仍保留（兼容旧调用点）
    - 但不再触碰 locations 表
    """
    return int(loc)


async def ensure_wh_loc_item(
    session: AsyncSession,
    *,
    wh: int,
    loc: int,
    item: int,
    code: Optional[str] = None,
    name: Optional[str] = None,
) -> None:
    """
    Phase M-5+（终态）：
    - locations 表已物理删除；此 helper 仅确保 warehouse + item 存在。
    - loc/code/name 参数仅为兼容旧测试调用点，禁止再写入/查询 locations。
    """
    _ = loc
    _ = code
    _ = name

    await session.execute(
        SA("INSERT INTO warehouses (id, name) VALUES (:w, 'WH') ON CONFLICT (id) DO NOTHING"),
        {"w": int(wh)},
    )

    # Phase M：items policy NOT NULL → 统一走最小合法 helper
    await ensure_item(session, id=int(item), sku=f"SKU-{item}", name=f"ITEM-{item}")


async def _ensure_supplier_lot(session: AsyncSession, *, wh: int, item: int, code: str) -> int:
    """
    Lot-World 终态：lots 只承载结构身份 + 必要快照，不承载 production_date/expiry_date/expiry_source 等日期事实。
    唯一性：uq_lots_wh_item_lot_code => (warehouse_id,item_id,lot_code) WHERE lot_code IS NOT NULL
    """
    row = (
        await session.execute(
            SA(
                """
                INSERT INTO lots(
                    warehouse_id,
                    item_id,
                    lot_code_source,
                    lot_code,
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
                    :code,
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
                ON CONFLICT (warehouse_id, item_id, lot_code)
                WHERE lot_code IS NOT NULL
                DO UPDATE SET lot_code_source = EXCLUDED.lot_code_source
                RETURNING id
                """
            ),
            {"w": int(wh), "i": int(item), "code": str(code)},
        )
    ).first()

    if not row:
        raise ValueError(f"failed to ensure SUPPLIER lot for wh={wh}, item={item}, code={code}")
    return int(row[0])


async def _ensure_internal_lot(session: AsyncSession, *, wh: int, item: int, ref: str) -> int:
    """
    INTERNAL lot 必须满足：
    - source_receipt_id/source_line_no NOT NULL（DB check）
    """
    r = await session.execute(
        SA(
            """
            INSERT INTO inbound_receipts (
                warehouse_id,
                source_type,
                source_id,
                ref,
                trace_id,
                status,
                remark,
                occurred_at
            )
            VALUES (
                :wh,
                'PO',
                NULL,
                :ref,
                NULL,
                'DRAFT',
                'UT internal lot source receipt',
                :occurred_at
            )
            RETURNING id
            """
        ),
        {"wh": int(wh), "ref": str(ref), "occurred_at": datetime.now(UTC)},
    )
    receipt_id = int(r.scalar_one())

    r2 = await session.execute(
        SA(
            """
            INSERT INTO lots (
                warehouse_id,
                item_id,
                lot_code_source,
                lot_code,
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
                :wh,
                it.id,
                'INTERNAL',
                NULL,
                :receipt_id,
                1,
                now(),
                it.shelf_life_value,
                it.shelf_life_unit,
                it.lot_source_policy,
                it.expiry_policy,
                it.derivation_allowed,
                it.uom_governance_enabled
            FROM items it
            WHERE it.id = :i
            RETURNING id
            """
        ),
        {"wh": int(wh), "i": int(item), "receipt_id": int(receipt_id)},
    )
    return int(r2.scalar_one())


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
    测试造数（Lot-World 终态）：
    - 主事实：lots + stocks_lot
    - code 语义：作为 lot_code（SUPPLIER）展示码
    - locations 已删除：loc 视作 warehouse_id（历史兼容）
    """
    wh = _wh_from_loc(loc)
    _ = date.today() + timedelta(days=days)  # days 仅保留参数形态（lots 不再承载日期事实）
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
    """
    测试口径：以 stocks_lot 为准。
    locations 已删除：loc 视作 warehouse_id。
    """
    wh = _wh_from_loc(loc)
    row = await session.execute(
        SA("SELECT COALESCE(SUM(qty),0) FROM stocks_lot WHERE item_id=:i AND warehouse_id=:w"),
        {"i": int(item), "w": int(wh)},
    )
    return int(row.scalar_one() or 0)


async def available(session: AsyncSession, *, item: int, loc: int) -> int:
    """
    测试口径：当前可售与在库一致（以 stocks_lot 为准）。
    locations 已删除：loc 视作 warehouse_id。
    """
    return await sum_on_hand(session, item=item, loc=loc)


async def qty_by_code(session: AsyncSession, *, item: int, loc: int, code: str) -> int:
    """
    按 lot_code 汇总 qty（stocks_lot + lots）。
    locations 已删除：loc 视作 warehouse_id。
    """
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
    """
    stock_snapshots 终态：
    - 粒度：(snapshot_date, warehouse_id, item_id, lot_id)
    - 不存在 batch_code 列
    - qty_allocated/qty_available/qty 必须满足 ck_stock_snapshots_qty_balance
    locations 已删除：loc 视作 warehouse_id。
    """
    _ = ts
    wh = _wh_from_loc(loc)

    # 快照必须绑定真实 lot_id；这里用 INTERNAL lot 承载“无指定展示码”的快照场景
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
