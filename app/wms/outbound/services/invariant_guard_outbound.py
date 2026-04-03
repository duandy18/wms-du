# app/wms/outbound/services/invariant_guard_outbound.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import raise_problem

UTC = timezone.utc


async def _load_last_after_qty_for_ref_lot(
    session: AsyncSession,
    *,
    ref: str,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
) -> Optional[int]:
    """
    终态不变量（lot-world）：
    - 不对比 Σ(delta)（会被 opening/seed/历史累计影响，且不是“局部事务校验”）
    - 对比“本 ref 最后一条 ledger.after_qty” 与 stocks_lot.qty
    """
    row = (
        await session.execute(
            text(
                """
                SELECT after_qty
                  FROM stock_ledger
                 WHERE ref = :ref
                   AND warehouse_id = :w
                   AND item_id = :i
                   AND lot_id = :lot
                 ORDER BY occurred_at DESC, id DESC
                 LIMIT 1
                """
            ),
            {"ref": str(ref), "w": int(warehouse_id), "i": int(item_id), "lot": int(lot_id)},
        )
    ).first()
    if not row:
        return None
    return int(row[0])


async def _load_stocks_lot_qty(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_id: int,
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT COALESCE(qty, 0)
                  FROM stocks_lot
                 WHERE warehouse_id = :w
                   AND item_id = :i
                   AND lot_id = :lot
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "lot": int(lot_id)},
        )
    ).first()
    return int((row[0] if row else 0) or 0)


async def _load_touched_lots_by_ref(
    session: AsyncSession,
    *,
    ref: str,
) -> Set[Tuple[int, int, int]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT DISTINCT warehouse_id, item_id, lot_id
                  FROM stock_ledger
                 WHERE ref = :ref
                """
            ),
            {"ref": str(ref)},
        )
    ).all()

    return {(int(r[0]), int(r[1]), int(r[2])) for r in rows}


async def enforce_outbound_invariant_guard(
    session: AsyncSession,
    *,
    ref: str,
    effects: Optional[Iterable[Dict[str, Any]]] = None,
    at: Optional[datetime] = None,
) -> None:
    debug_ref = str(ref)
    ts = at or datetime.now(UTC)

    touched: Set[Tuple[int, int, int]] = set()

    if effects is None:
        touched = await _load_touched_lots_by_ref(session, ref=debug_ref)
    else:
        for eff in effects:
            touched.add(
                (
                    int(eff["warehouse_id"]),
                    int(eff["item_id"]),
                    int(eff["lot_id"]),
                )
            )

    if not touched:
        return

    mismatches: List[Dict[str, Any]] = []

    for wh_id, item_id, lot_id in sorted(touched):
        last_after_qty = await _load_last_after_qty_for_ref_lot(
            session,
            ref=debug_ref,
            warehouse_id=wh_id,
            item_id=item_id,
            lot_id=lot_id,
        )
        # 如果本 ref 没有对应维度的 ledger 行，说明 touched 计算不一致；直接报错更合理
        if last_after_qty is None:
            mismatches.append(
                {
                    "warehouse_id": wh_id,
                    "item_id": item_id,
                    "lot_id": lot_id,
                    "reason": "no_ledger_row_for_ref",
                }
            )
            continue

        stocks_qty = await _load_stocks_lot_qty(
            session,
            warehouse_id=wh_id,
            item_id=item_id,
            lot_id=lot_id,
        )

        if int(last_after_qty) != int(stocks_qty):
            mismatches.append(
                {
                    "warehouse_id": wh_id,
                    "item_id": item_id,
                    "lot_id": lot_id,
                    "ledger_ref_last_after_qty": int(last_after_qty),
                    "stocks_lot_qty": int(stocks_qty),
                }
            )

    if mismatches:
        raise_problem(
            status_code=409,
            error_code="invariant_guard_failed",
            message="执行域不变量校验失败：ref 内最后一条 ledger.after_qty 与 stocks_lot.qty 不一致。",
            context={"ref": debug_ref, "at": ts.isoformat()},
            details=mismatches,
        )
