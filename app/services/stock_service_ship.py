# app/services/stock_service_ship.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.services.three_books_enforcer import enforce_three_books

AdjustFn = Callable[..., Awaitable[Dict[str, Any]]]


def _shortage_detail(
    *,
    item_id: int,
    batch_code: Optional[str],
    available_qty: int,
    required_qty: int,
    path: str,
) -> Dict[str, Any]:
    short_qty = max(0, int(required_qty) - int(available_qty))
    return {
        "type": "shortage",
        "path": path,
        "item_id": int(item_id),
        "batch_code": batch_code,
        "required_qty": int(required_qty),
        "available_qty": int(available_qty),
        "short_qty": int(short_qty),
        # ✅ 兼容/同义字段（保留）
        "shortage_qty": int(short_qty),
        "need": int(required_qty),
        "on_hand": int(available_qty),
        "shortage": int(short_qty),
        "reason": "insufficient_stock",
    }


async def _load_total_available_qty(session: AsyncSession, *, warehouse_id: int, item_id: int) -> int:
    """
    当 FEFO 找不到任何可用 stocks 行时，回读总可用 qty 作为 available_qty（通常为 0）。
    """
    row = (
        await session.execute(
            text(
                """
                SELECT COALESCE(SUM(qty), 0)
                  FROM stocks
                 WHERE warehouse_id=:w AND item_id=:i AND qty>0
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id)},
        )
    ).first()
    try:
        return int((row[0] if row else 0) or 0)
    except Exception:
        return 0


async def ship_commit_direct_impl(
    *,
    session: AsyncSession,
    warehouse_id: int,
    platform: str,
    shop_id: str,
    ref: str,
    lines: list[dict[str, int]],
    occurred_at: Optional[datetime],
    trace_id: Optional[str],
    utc_now: Callable[[], datetime],
    adjust_fn: AdjustFn,
) -> Dict[str, Any]:
    """
    本方法保持原有行为，但 FEFO 选择更稳定（优先 expiry_date，再按 stock_id 排序）。

    Phase 3.10（本次）：
    - 引入 sub_reason（业务细分）：
      直接发货/出库链路统一标记为 ORDER_SHIP（若未来需要区分 INTERNAL_SHIP，可在调用方传 meta 覆盖）。

    Phase 3（三库一致性工程化）：
    - commit 成功的必要条件：ledger + stocks + snapshot 可观测一致（对本次 touched keys）
    """
    _ = platform
    _ = shop_id

    ts = occurred_at or utc_now()

    need_by_item: Dict[int, int] = {}
    for line in lines or []:
        item = int(line["item_id"])
        qty = int(line["qty"])
        need_by_item[item] = need_by_item.get(item, 0) + qty

    if not need_by_item:
        return {"idempotent": True, "applied": False, "ref": ref, "total_qty": 0}

    idempotent = True
    total = 0

    # Phase 3：收集本次出库的 effects，用于三库一致性验证
    effects: list[Dict[str, Any]] = []

    for item_id, want in need_by_item.items():
        existing = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(delta), 0)
                  FROM stock_ledger
                 WHERE warehouse_id=:w AND item_id=:i
                   AND ref=:ref AND delta < 0
                """
            ),
            {"w": int(warehouse_id), "i": item_id, "ref": ref},
        )
        already = int(existing.scalar() or 0)
        need = want + already
        if need <= 0:
            continue

        idempotent = False
        remain = need

        while remain > 0:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT s.batch_code, s.qty
                          FROM stocks s
                          LEFT JOIN batches b
                            ON b.item_id      = s.item_id
                           AND b.warehouse_id = s.warehouse_id
                           AND b.batch_code IS NOT DISTINCT FROM s.batch_code
                         WHERE s.item_id=:i AND s.warehouse_id=:w AND s.qty>0
                         ORDER BY b.expiry_date ASC NULLS LAST, s.id ASC
                         LIMIT 1
                        """
                    ),
                    {"i": item_id, "w": int(warehouse_id)},
                )
            ).first()

            if not row:
                available = await _load_total_available_qty(session, warehouse_id=int(warehouse_id), item_id=int(item_id))
                raise_problem(
                    status_code=409,
                    error_code="insufficient_stock",
                    message="库存不足，禁止提交出库。",
                    context={
                        "warehouse_id": int(warehouse_id),
                        "item_id": int(item_id),
                        "ref": str(ref),
                    },
                    details=[
                        _shortage_detail(
                            item_id=int(item_id),
                            batch_code=None,
                            available_qty=int(available),
                            required_qty=int(remain),
                            path=f"ship_commit_direct[item_id={int(item_id)}]",
                        )
                    ],
                    next_actions=[
                        {"action": "rescan_stock", "label": "刷新库存"},
                        {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                    ],
                )

            # ✅ 关键：batch_code 允许为 None（无批次槽位），绝不能 str(None) 变成 'None'
            batch_code = row[0]
            on_hand = int(row[1])
            take = min(remain, on_hand)

            await adjust_fn(
                session=session,
                item_id=item_id,
                warehouse_id=warehouse_id,
                delta=-take,
                reason=MovementType.SHIP,
                ref=ref,
                ref_line=1,
                occurred_at=ts,
                batch_code=batch_code,
                trace_id=trace_id,
                meta={
                    "sub_reason": "ORDER_SHIP",
                },
            )

            # 记录 effect（delta 为负数）
            effects.append(
                {
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(item_id),
                    "batch_code": batch_code,
                    "qty": -int(take),
                    "ref": str(ref),
                    "ref_line": 1,
                }
            )

            remain -= take
            total += take

    # Phase 3：强一致尾门（仅在本次实际扣减时执行）
    if effects:
        await enforce_three_books(session, ref=str(ref), effects=effects, at=ts)

    return {
        "idempotent": idempotent,
        "applied": not idempotent,
        "ref": ref,
        "total_qty": total,
    }
