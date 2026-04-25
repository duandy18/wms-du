# tests/helpers/inventory.py
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import text as SA
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.stock.services.lot_service import ensure_internal_lot_singleton as ensure_internal_lot_singleton_svc
from app.wms.stock.services.lot_service import ensure_lot_full as ensure_lot_full_svc
from app.wms.stock.services.stock_adjust import adjust_lot_impl
from tests.utils.ensure_minimal import ensure_item

UTC = timezone.utc

__all__ = [
    "_has_table",
    "_columns_of",
    "ensure_wh_loc_item",
    "seed_supplier_lot_slot",
    "seed_many",
    "qty_by_lot_code",
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


def _stable_required_dates_from_code(code_raw: str, *, days: int) -> tuple[date, date]:
    """
    REQUIRED lot helper：按 lot_code 稳定生成日期，避免不同批次都撞到同一天 production_date。

    规则：
    - 同一 code -> 同一 production_date
    - 不同 code -> 大概率不同 production_date
    - expiry_date = production_date + days
    """
    code = str(code_raw).strip()
    if not code:
        raise ValueError("code empty")

    digest = hashlib.sha1(code.encode("utf-8")).hexdigest()
    offset_days = int(digest[:8], 16) % 73000  # ~200 years range, collision risk much lower than using today
    production_date = date(2000, 1, 1) + timedelta(days=offset_days)
    expiry_date = production_date + timedelta(days=int(days))
    return production_date, expiry_date


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


async def seed_supplier_lot_slot(
    session: AsyncSession,
    *,
    item: int,
    loc: int,
    lot_code: str,
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
    - seed_supplier_lot_slot 的语义就是“造一个 SUPPLIER lot slot”，因此商品必须走 REQUIRED
    - REQUIRED 且发生入库（delta>0）时，必须提供 production/expiry 事实
    """
    wh = _wh_from_loc(loc)
    code_raw = str(lot_code).strip()
    if not code_raw:
        raise ValueError("code empty")

    # 确保主数据存在（很多测试假设 item/wh 已存在）
    await session.execute(
        SA("INSERT INTO warehouses (id, name) VALUES (:w, 'WH') ON CONFLICT (id) DO NOTHING"),
        {"w": int(wh)},
    )

    # 当前 helper 语义就是“造 batch slot”，因此显式把商品设为 REQUIRED。
    # 不能用 ensure_item 默认值（expiry_required=False），否则会把上游已设好的 REQUIRED 冲回 NONE。
    await ensure_item(
        session,
        id=int(item),
        sku=f"SKU-{item}",
        name=f"ITEM-{item}",
        expiry_required=True,
    )

    expiry_policy = await _load_item_expiry_policy(session, item_id=int(item))

    if expiry_policy == "REQUIRED":
        production_date, expiry_date = _stable_required_dates_from_code(code_raw, days=int(days))
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

    if expiry_policy == "REQUIRED" and int(delta) > 0 and expiry_date is None:
        production_date, expiry_date = _stable_required_dates_from_code(code_raw, days=int(days))

    ref = f"ut:seed_supplier_lot_slot:set:{int(wh)}:{int(item)}:{code_raw}:{int(target)}"

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
    )


async def seed_many(session: AsyncSession, entries: Iterable[Tuple[int, int, str, int, int]]) -> None:
    for item, loc, code, qty, days in entries:
        await seed_supplier_lot_slot(session, item=item, loc=loc, lot_lot_code=code, qty=qty, days=days)


async def sum_on_hand(session: AsyncSession, *, item: int, loc: int) -> int:
    wh = _wh_from_loc(loc)
    row = await session.execute(
        SA("SELECT COALESCE(SUM(qty),0) FROM stocks_lot WHERE item_id=:i AND warehouse_id=:w"),
        {"i": int(item), "w": int(wh)},
    )
    return int(row.scalar_one() or 0)


async def available(session: AsyncSession, *, item: int, loc: int) -> int:
    return await sum_on_hand(session, item=item, loc=loc)


async def qty_by_lot_code(session: AsyncSession, *, item: int, loc: int, lot_code: str) -> int:
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
        {"i": int(item), "w": int(wh), "code": str(lot_code)},
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
