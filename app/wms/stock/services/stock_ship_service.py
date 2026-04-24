# app/wms/stock/services/stock_ship_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import raise_problem
from app.wms.shared.enums import MovementType
from app.wms.outbound.services.invariant_guard_outbound import enforce_outbound_invariant_guard
from app.wms.shared.services.lot_code_contract import fetch_item_expiry_policy_map

AdjustLotFn = Callable[..., Awaitable[Dict[str, Any]]]
UTC = timezone.utc


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


async def _load_total_available_qty(session: AsyncSession, *, warehouse_id: int, item_id: int) -> int:
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


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


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
    """
    Batch-as-Lot 终态：禁止执行域自动挑 lot（包括 FEFO）。

    - REQUIRED 商品：必须显式批次（但本函数 lines 不含 batch_code），因此直接拒绝。
    - NONE 商品：batch_code 必须为 null，统一扣 INTERNAL 槽位（lots.lot_code IS NULL）。
    """
    ts = occurred_at or datetime.now(UTC)

    need_by_item: Dict[int, int] = {}
    for line in lines or []:
        item = int(line["item_id"])
        qty = int(line["qty"])
        need_by_item[item] = need_by_item.get(item, 0) + qty

    if not need_by_item:
        return {"idempotent": True, "applied": False, "ref": ref, "total_qty": 0}

    pol_map = await fetch_item_expiry_policy_map(session, set(need_by_item.keys()))
    missing = [i for i in sorted(need_by_item.keys()) if i not in pol_map]
    if missing:
        raise_problem(
            status_code=422,
            error_code="unknown_item",
            message="未知商品，禁止出库。",
            details=[{"type": "validation", "path": "lines", "item_ids": missing, "reason": "unknown_item"}],
        )

    idempotent = True
    total = 0
    effects: list[Dict[str, Any]] = []

    for item_id, want in need_by_item.items():
        requires_batch = _requires_batch_from_expiry_policy(pol_map.get(int(item_id)))

        if requires_batch:
            # 执行域必须显式批次；本函数没有 batch_code 入参 => 直接拒绝，防止暗中 FEFO
            raise_problem(
                status_code=422,
                error_code="batch_required",
                message="批次受控商品必须提供批次，禁止自动挑选批次出库。",
                details=[{"type": "batch", "path": "lines[item_id]", "item_id": int(item_id), "reason": "batch_code_required"}],
                next_actions=[{"action": "provide_batch_code", "label": "按行提供 batch_code 后重试"}],
            )

        # NONE：允许执行（扣 INTERNAL 槽位）
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

        # 只选 INTERNAL 槽位：lots.lot_code IS NULL
        row = (
            await session.execute(
                text(
                    """
                    SELECT s.lot_id, s.qty
                      FROM stocks_lot s
                      JOIN lots lo
                        ON lo.id = s.lot_id
                       AND lo.warehouse_id = s.warehouse_id
                       AND lo.item_id = s.item_id
                     WHERE s.item_id = :i
                       AND s.warehouse_id = :w
                       AND s.qty > 0
                       AND lo.lot_code IS NULL
                     ORDER BY s.lot_id ASC
                     LIMIT 1
                     FOR UPDATE OF s
                    """
                ),
                {"i": int(item_id), "w": int(warehouse_id)},
            )
        ).first()

        if not row:
            available = await _load_total_available_qty(session, warehouse_id=int(warehouse_id), item_id=int(item_id))
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                details=[_shortage_detail(item_id=int(item_id), available_qty=int(available), required_qty=int(need))],
            )

        lot_id = int(row[0])
        on_hand = int(row[1] or 0)
        take = min(int(need), int(on_hand))
        if take <= 0:
            available = await _load_total_available_qty(session, warehouse_id=int(warehouse_id), item_id=int(item_id))
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                details=[_shortage_detail(item_id=int(item_id), available_qty=int(available), required_qty=int(need))],
            )

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
            batch_code=None,
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
        total += int(take)

        if int(need) > int(take):
            available = await _load_total_available_qty(session, warehouse_id=int(warehouse_id), item_id=int(item_id))
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                details=[_shortage_detail(item_id=int(item_id), available_qty=int(available), required_qty=int(need - take))],
            )

    if effects:
        await enforce_outbound_invariant_guard(session, ref=str(ref), effects=effects, at=ts)

    return {"idempotent": bool(idempotent), "applied": not bool(idempotent), "ref": str(ref), "total_qty": int(total)}
