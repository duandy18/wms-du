# app/services/stock_service_ship.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.services.invariant_guard_outbound import enforce_outbound_invariant_guard

AdjustLotFn = Callable[..., Awaitable[Dict[str, Any]]]


def _shortage_detail(
    *,
    item_id: int,
    available_qty: int,
    required_qty: int,
) -> Dict[str, Any]:
    short_qty = max(0, int(required_qty) - int(available_qty))
    return {
        "type": "shortage",
        "item_id": int(item_id),
        "required_qty": int(required_qty),
        "available_qty": int(available_qty),
        "short_qty": int(short_qty),
        "reason": "insufficient_stock",
    }


async def _load_total_available_qty(
    session: AsyncSession, *, warehouse_id: int, item_id: int
) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT COALESCE(SUM(qty), 0)
                  FROM stocks_lot
                 WHERE warehouse_id=:w AND item_id=:i AND qty>0
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
    ).first()
    return int((row[0] if row else 0) or 0)


async def ship_commit_direct_lot_impl(
    *,
    session: AsyncSession,
    warehouse_id: int,
    ref: str,
    lines: list[dict[str, int]],
    occurred_at: Optional[datetime],
    trace_id: Optional[str],
    adjust_lot_fn: AdjustLotFn,
) -> Dict[str, Any]:
    ts = occurred_at or datetime.utcnow()

    need_by_item: Dict[int, int] = {}
    for line in lines or []:
        item = int(line["item_id"])
        qty = int(line["qty"])
        need_by_item[item] = need_by_item.get(item, 0) + qty

    if not need_by_item:
        return {"idempotent": True, "applied": False, "ref": ref, "total_qty": 0}

    idempotent = True
    total = 0
    effects: list[Dict[str, Any]] = []

    for item_id, want in need_by_item.items():
        existing = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(delta), 0)
                  FROM stock_ledger
                 WHERE warehouse_id=:w
                   AND item_id=:i
                   AND ref=:ref
                   AND delta < 0
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "ref": str(ref)},
        )
        already = int(existing.scalar() or 0)
        need = int(want) + int(already)
        if need <= 0:
            continue

        idempotent = False
        remain = int(need)

        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        s.lot_id,
                        s.qty,
                        lo.lot_code,
                        lo.expiry_date
                    FROM stocks_lot s
                    LEFT JOIN lots lo ON lo.id = s.lot_id
                    WHERE s.item_id = :i
                      AND s.warehouse_id = :w
                      AND s.qty > 0
                    ORDER BY lo.expiry_date ASC NULLS LAST, s.lot_id ASC
                    FOR UPDATE OF s
                    """
                ),
                {"i": int(item_id), "w": int(warehouse_id)},
            )
        ).all()

        if not rows:
            available = await _load_total_available_qty(
                session, warehouse_id=int(warehouse_id), item_id=int(item_id)
            )
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                details=[
                    _shortage_detail(
                        item_id=int(item_id),
                        available_qty=int(available),
                        required_qty=int(remain),
                    )
                ],
            )

        for r in rows:
            if remain <= 0:
                break

            lot_id = int(r.lot_id)
            on_hand = int(r.qty or 0)
            lot_code = r.lot_code

            if on_hand <= 0:
                continue

            take = min(remain, on_hand)
            if take <= 0:
                continue

            ref_line = int(len(effects) + 1)

            await adjust_lot_fn(
                session=session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                lot_id=int(lot_id),
                delta=-int(take),
                reason=MovementType.SHIP,
                ref=str(ref),
                ref_line=int(ref_line),
                occurred_at=ts,
                trace_id=trace_id,
                batch_code=(str(lot_code) if lot_code else None),
                meta={"sub_reason": "ORDER_SHIP"},
            )

            effects.append(
                {
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(item_id),
                    "lot_id": int(lot_id),
                    "qty": -int(take),
                    "ref": str(ref),
                    "ref_line": int(ref_line),
                }
            )

            remain -= int(take)
            total += int(take)

        if remain > 0:
            available = await _load_total_available_qty(
                session, warehouse_id=int(warehouse_id), item_id=int(item_id)
            )
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                details=[
                    _shortage_detail(
                        item_id=int(item_id),
                        available_qty=int(available),
                        required_qty=int(remain),
                    )
                ],
            )

    if effects:
        await enforce_outbound_invariant_guard(
            session, ref=str(ref), effects=effects, at=ts
        )

    return {"idempotent": bool(idempotent), "applied": not bool(idempotent), "ref": str(ref), "total_qty": int(total)}
