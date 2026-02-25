# app/services/scan_handlers/count_handler.py
from __future__ import annotations

from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService
from app.services.three_books_enforcer import enforce_three_books
from app.services.utils.expiry_resolver import resolve_batch_dates_for_item


async def _ensure_supplier_lot_id(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
    production_date: date | None,
    expiry_date: date | None,
) -> int:
    """
    Phase 4E：Count 写入以 lot-world 为准。
    - 把 batch_code 视为展示码（lots.lot_code）
    - COUNT 的维度需要落在一个确定的 lot 槽位上，因此这里确保 SUPPLIER lot 存在并返回 id
    """
    code = str(lot_code).strip()
    if not code:
        raise ValueError("盘点操作必须提供 batch_code。")

    prod = production_date or date.today()
    expiry_source = "EXPLICIT" if expiry_date is not None else None

    row = await session.execute(
        sa.text(
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
            VALUES (:w, :i, 'SUPPLIER', :code, :prod, :exp, :exp_src)
            ON CONFLICT (warehouse_id, item_id, lot_code_source, lot_code)
            WHERE lot_code_source = 'SUPPLIER'
            DO UPDATE SET expiry_date = EXCLUDED.expiry_date
            RETURNING id
            """
        ),
        {
            "w": int(warehouse_id),
            "i": int(item_id),
            "code": code,
            "prod": prod,
            "exp": expiry_date,
            "exp_src": expiry_source,
        },
    )
    got = row.scalar_one_or_none()
    if got is not None:
        return int(got)

    row2 = await session.execute(
        sa.text(
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
        {"w": int(warehouse_id), "i": int(item_id), "code": code},
    )
    got2 = row2.scalar_one_or_none()
    if got2 is None:
        raise ValueError("lot_not_found")
    return int(got2)


async def _ensure_stocks_lot_slot_exists(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
) -> None:
    await session.execute(
        sa.text(
            """
            INSERT INTO stocks_lot (item_id, warehouse_id, lot_id, qty)
            VALUES (:i, :w, :lot, 0)
            ON CONFLICT ON CONSTRAINT uq_stocks_lot_item_wh_lot DO NOTHING
            """
        ),
        {"i": int(item_id), "w": int(warehouse_id), "lot": int(lot_id)},
    )


async def _lock_current_qty_by_lot(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
) -> int:
    """
    Phase 4E：按确定 lot 槽位加锁读取 current qty（避免聚合 FOR UPDATE 的尴尬）。
    """
    await _ensure_stocks_lot_slot_exists(session, warehouse_id=warehouse_id, item_id=item_id, lot_id=lot_id)

    row = await session.execute(
        sa.text(
            """
            SELECT qty
              FROM stocks_lot
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_id_key   = :lk
             FOR UPDATE
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "lk": int(lot_id)},
    )
    return int(row.scalar_one_or_none() or 0)


async def _refresh_snapshot_for_item(
    session: AsyncSession,
    *,
    snapshot_date: date,
    warehouse_id: int,
    item_id: int,
) -> None:
    """
    Phase 3 合同要求：delta != 0 时 snapshot 必须与余额可观测一致（至少 touched keys）。

    Phase 4E：
    - snapshot 从 lot-world 余额（stocks_lot）重建；
    - batch_code 字段作为展示码：lots.lot_code（允许 NULL）。
    """
    await session.execute(
        sa.text(
            """
            DELETE FROM stock_snapshots
            WHERE snapshot_date = :d
              AND warehouse_id  = :w
              AND item_id       = :i
            """
        ),
        {"d": snapshot_date, "w": int(warehouse_id), "i": int(item_id)},
    )

    # 注意：batch_code_key 是生成列，INSERT 不写；唯一性在 (snapshot_date, warehouse_id, item_id, batch_code_key)
    await session.execute(
        sa.text(
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
            SELECT
                :d AS snapshot_date,
                s.warehouse_id,
                s.item_id,
                lo.lot_code AS batch_code,
                s.qty,
                s.qty AS qty_available,
                0    AS qty_allocated
              FROM stocks_lot s
              LEFT JOIN lots lo ON lo.id = s.lot_id
             WHERE s.warehouse_id = :w
               AND s.item_id      = :i
            """
        ),
        {"d": snapshot_date, "w": int(warehouse_id), "i": int(item_id)},
    )


async def handle_count(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    batch_code: str,
    actual: int,
    ref: str,
    production_date: date | None = None,
    expiry_date: date | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    盘点（Count）—— v2：按 仓库 + 商品 + 批次展示码(lot_code) 粒度。

    Phase 3 合同：
    - delta != 0：写 ledger + 改余额 + snapshot 可观测一致
    - delta == 0：也写一条“确认类事件台账”（ledger），余额不变
      * 通过 StockService.adjust 的 allow_zero_delta_ledger + sub_reason 实现

    Phase 4E：
    - current/余额以 stocks_lot 为准；
    - 禁止读取 legacy stocks。
    """
    if actual < 0:
        raise ValueError("Actual quantity must be non-negative.")
    if not batch_code or not str(batch_code).strip():
        raise ValueError("盘点操作必须提供 batch_code。")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("盘点操作必须明确 warehouse_id。")

    bcode = str(batch_code).strip()

    # 只有盘盈需要按“入库”逻辑补齐日期
    if actual > 0:
        # 对批次展示码（SUPPLIER lot）而言，建议至少有一个日期可推导/显式提供
        if production_date is None and expiry_date is None:
            # 只在需要增加库存（delta>0）时强制；这里先不强制，后面按 delta 再判断
            pass

    # Phase 4E：确保 lot 存在并锁定该 lot 槽位读取 current
    # ⚠️ 这里将 batch_code 视为 SUPPLIER lot_code
    # 日期：仅当盘盈时强制补齐；盘亏/确认不要求
    lot_id = await _ensure_supplier_lot_id(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_code=bcode,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    current = await _lock_current_qty_by_lot(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=int(lot_id),
    )

    delta = int(actual) - int(current)
    before = int(current)
    after = int(current) + int(delta)

    # 只有盘盈需要按“入库”逻辑补齐日期
    if delta > 0:
        if production_date is None and expiry_date is None:
            raise ValueError("盘盈为入库行为，必须提供 production_date 或 expiry_date。")

        production_date, expiry_date = await resolve_batch_dates_for_item(
            session,
            item_id=item_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    meta = {
        "sub_reason": "COUNT_ADJUST" if delta != 0 else "COUNT_CONFIRM",
    }
    if delta == 0:
        meta["allow_zero_delta_ledger"] = True

    stock_svc = StockService()
    await stock_svc.adjust(
        session=session,
        item_id=item_id,
        warehouse_id=int(warehouse_id),
        delta=int(delta),
        reason=MovementType.COUNT,
        ref=str(ref),
        ref_line=1,
        batch_code=bcode,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=trace_id,
        meta=meta,
        lot_id=int(lot_id),
    )

    ts = datetime.now(timezone.utc)

    # ✅ Phase 3 合同：delta!=0 时刷新当日 snapshot，使其与余额可观测一致
    if delta != 0:
        await _refresh_snapshot_for_item(
            session,
            snapshot_date=ts.date(),
            warehouse_id=int(warehouse_id),
            item_id=int(item_id),
        )

    await enforce_three_books(
        session,
        ref=str(ref),
        effects=[
            {
                "warehouse_id": int(warehouse_id),
                "item_id": int(item_id),
                "batch_code": str(bcode),
                "qty": int(delta),
                "ref": str(ref),
                "ref_line": 1,
            }
        ],
        at=ts,
    )

    return {
        "item_id": int(item_id),
        "warehouse_id": int(warehouse_id),
        "batch_code": str(batch_code),
        "actual": int(actual),
        "delta": int(delta),
        "before": int(before),
        "after": int(after),
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
