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
    Phase 2：Lot upsert 收口到 app/services/stock/lots.py（ensure_lot_full）
    - Count 仍要求 batch_code（盘点维度必须落到确定 SUPPLIER lot 槽位）
    """
    from app.services.stock.lots import ensure_lot_full

    _ = production_date
    _ = expiry_date

    code = str(lot_code).strip()
    if not code:
        raise ValueError("盘点操作必须提供 batch_code。")

    return await ensure_lot_full(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_code=str(code),
        production_date=None,
        expiry_date=None,
    )


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
    await _ensure_stocks_lot_slot_exists(session, warehouse_id=warehouse_id, item_id=item_id, lot_id=lot_id)

    row = await session.execute(
        sa.text(
            """
            SELECT qty
              FROM stocks_lot
             WHERE warehouse_id = :w
               AND item_id      = :i
               AND lot_id       = :lot
             FOR UPDATE
            """
        ),
        {"w": int(warehouse_id), "i": int(item_id), "lot": int(lot_id)},
    )
    return int(row.scalar_one_or_none() or 0)


async def _refresh_snapshot_for_item(
    session: AsyncSession,
    *,
    snapshot_date: date,
    warehouse_id: int,
    item_id: int,
) -> None:
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

    # Lot-world: snapshot grain is (snapshot_date, warehouse_id, item_id, lot_id).
    # Do NOT write batch_code into stock_snapshots (column no longer exists).
    await session.execute(
        sa.text(
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
            SELECT
                :d AS snapshot_date,
                s.warehouse_id,
                s.item_id,
                s.lot_id,
                s.qty,
                s.qty AS qty_available,
                0    AS qty_allocated
              FROM stocks_lot s
             WHERE s.warehouse_id = :w
               AND s.item_id      = :i
            ON CONFLICT (snapshot_date, warehouse_id, item_id, lot_id)
            DO UPDATE SET
                qty = EXCLUDED.qty,
                qty_available = EXCLUDED.qty_available,
                qty_allocated = EXCLUDED.qty_allocated
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
    if actual < 0:
        raise ValueError("Actual quantity must be non-negative.")
    if not batch_code or not str(batch_code).strip():
        raise ValueError("盘点操作必须提供 batch_code。")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("盘点操作必须明确 warehouse_id。")

    bcode = str(batch_code).strip()

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

    if delta > 0:
        if production_date is None and expiry_date is None:
            raise ValueError("盘盈为入库行为，必须提供 production_date 或 expiry_date。")

        production_date, expiry_date = await resolve_batch_dates_for_item(
            session,
            item_id=item_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )

    meta = {"sub_reason": "COUNT_ADJUST" if delta != 0 else "COUNT_CONFIRM"}
    if delta == 0:
        meta["allow_zero_delta_ledger"] = True

    # ✅ 任务3 终态：Count 已持有 authoritative lot_id，必须走 adjust_lot（lot-only 原语入口）
    stock_svc = StockService()
    await stock_svc.adjust_lot(
        session=session,
        item_id=item_id,
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
        delta=int(delta),
        reason=MovementType.COUNT,
        ref=str(ref),
        ref_line=1,
        occurred_at=None,
        meta=meta,
        batch_code=bcode,
        production_date=production_date,
        expiry_date=expiry_date,
        trace_id=trace_id,
        shadow_write_stocks=False,
    )

    ts = datetime.now(timezone.utc)

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
