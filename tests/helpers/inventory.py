# tests/helpers/inventory.py
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.lot_service import ensure_internal_lot_singleton as ensure_internal_lot_singleton_svc
from app.services.lot_service import ensure_lot_full as ensure_lot_full_svc
from app.services.stock_adjust import adjust_lot_impl
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


def _as_lot_id(v: object) -> int:
    """
    lot_service 的 ensure_* 可能返回 int(lot_id) 或 ORM 对象（带 .id）。
    tests 侧用这个函数统一兼容，避免类型漂移导致的 AttributeError。
    """
    return int(getattr(v, "id", v))


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


async def _load_item_expiry_policy(session: AsyncSession, *, item_id: int) -> str:
    row = await session.execute(SA("SELECT expiry_policy::text FROM items WHERE id=:i"), {"i": int(item_id)})
    v = row.scalar_one_or_none()
    if v is None:
        raise ValueError(f"item_not_found: {item_id}")
    return str(v)


async def _get_stock_qty(session: AsyncSession, *, item: int, wh: int, lot_id: int) -> int:
    r = await session.execute(
        SA(
            """
            SELECT qty
              FROM stocks_lot
             WHERE item_id = :i
               AND warehouse_id = :w
               AND lot_id = :lot
             LIMIT 1
            """
        ),
        {"i": int(item), "w": int(wh), "lot": int(lot_id)},
    )
    v = r.scalar_one_or_none()
    return int(v) if v is not None else 0


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
    ✅ 统一 seed 入口（Phase M-5 终态）：

    - lot 创建：ensure_lot_full（禁止 tests 直接 INSERT INTO lots）
    - 库存写入：adjust_lot_impl（禁止 tests 直接 INSERT/UPDATE stocks_lot）
    - “设置为某个 qty”语义：读当前 qty -> delta -> adjust_lot_impl 写入
      （等价于旧实现的 ON CONFLICT DO UPDATE SET qty）

    关键：日期合同必须认真对待
    - 若 item.expiry_policy == 'REQUIRED' 且发生入库（delta>0），必须提供 expiry_date（production_date 可为空）
    - 若 item.expiry_policy == 'NONE'，日期一律传 None（避免伪造日期事实）
    """
    wh = _wh_from_loc(loc)
    code_raw = str(code).strip()
    if not code_raw:
        raise ValueError("code empty")

    # 确保主数据存在（很多测试假设 item/wh 已存在）
    await session.execute(
        SA("INSERT INTO warehouses (id, name) VALUES (:w, 'WH') ON CONFLICT (id) DO NOTHING"),
        {"w": int(wh)},
    )
    await ensure_item(session, id=int(item), sku=f"SKU-{item}", name=f"ITEM-{item}")

    expiry_policy = await _load_item_expiry_policy(session, item_id=int(item))

    # 先确保 lot（满足 ensure_lot_full 的强制入参）
    if expiry_policy == "REQUIRED":
        expiry_date: Optional[date] = date.today() + timedelta(days=int(days))
        production_date: Optional[date] = None
    else:
        expiry_date = None
        production_date = None

    got = await ensure_lot_full_svc(
        session,
        warehouse_id=int(wh),
        item_id=int(item),
        lot_code=code_raw,
        production_date=production_date,
        expiry_date=expiry_date,
    )
    lot_id = _as_lot_id(got)

    cur = await _get_stock_qty(session, item=int(item), wh=int(wh), lot_id=int(lot_id))
    target = int(qty)
    delta = target - int(cur)
    if delta == 0:
        return

    # 入库合同：REQUIRED 且 delta>0 必须提供 expiry_date
    if expiry_policy == "REQUIRED" and int(delta) > 0 and expiry_date is None:
        expiry_date = date.today() + timedelta(days=int(days))

    # 用 ref 携带 target，保证“重复 seed 同 qty”幂等，
    # 但“不同 qty 的 overwrite”不会被 idem 吃掉（等价于旧 DO UPDATE）。
    ref = f"ut:seed_batch_slot:set:{int(wh)}:{int(item)}:{code_raw}:{int(target)}"

    await adjust_lot_impl(
        session=session,
        item_id=int(item),
        warehouse_id=int(wh),
        lot_id=int(lot_id),
        delta=int(delta),
        reason="UT_SEED_BATCH_SLOT",
        ref=str(ref),
        ref_line=1,
        occurred_at=None,
        meta=None,
        batch_code=code_raw,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=None,
        utc_now=lambda: datetime.now(UTC),
        shadow_write_stocks=False,
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
    got = await ensure_internal_lot_singleton_svc(
        session,
        warehouse_id=int(wh),
        item_id=int(item),
    )
    lot_id = _as_lot_id(got)

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
