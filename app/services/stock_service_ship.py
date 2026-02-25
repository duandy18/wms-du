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
AdjustLotFn = Callable[..., Awaitable[Dict[str, Any]]]


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
    当 FEFO 找不到任何可用行时，回读总可用 qty 作为 available_qty（通常为 0）。

    Phase 4C/4D：
    - 总量读取以 stocks_lot 为准（lot-world 余额）
    """
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
    旧实现（batch-world）：

    Phase 4D：
    - 为避免执行链路口径回退，且为 Phase 4E（rename/drop stocks）铺路，
      此 batch-world 实现被明确禁用。
    - 正确入口：ship_commit_direct_lot_impl（lot-world）。

    说明：
    - 若确需回滚对照，应在独立 legacy 模块/分支中保留，不允许在主执行链路中读取 legacy stocks。
    """
    _ = session
    _ = warehouse_id
    _ = platform
    _ = shop_id
    _ = ref
    _ = lines
    _ = occurred_at
    _ = trace_id
    _ = utc_now
    _ = adjust_fn
    raise RuntimeError("ship_commit_direct_impl(batch-world) 已在 Phase 4D 禁用，请使用 ship_commit_direct_lot_impl。")


async def ship_commit_direct_lot_impl(
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
    adjust_lot_fn: AdjustLotFn,
) -> Dict[str, Any]:
    """
    Phase 4C 主实现（lot-world）：

    - 选槽：stocks_lot + lots（expiry_date ASC NULLS LAST, lot_id_key ASC）
    - 扣减：adjust_lot_fn（写 stocks_lot + ledger(lot_id)；可 shadow 写 stocks，但 Phase 4D 默认关闭）
    - 三账尾门：保持原 enforce_three_books（内部会 run_snapshot + verify）
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
            {"w": int(warehouse_id), "i": int(item_id), "ref": str(ref)},
        )
        already = int(existing.scalar() or 0)
        need = int(want) + int(already)
        if need <= 0:
            continue

        idempotent = False
        remain = int(need)

        # 锁定候选 lot 槽位（强一致）
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        s.lot_id,
                        s.lot_id_key,
                        s.qty,
                        lo.lot_code,
                        lo.expiry_date
                    FROM stocks_lot s
                    LEFT JOIN lots lo ON lo.id = s.lot_id
                    WHERE s.item_id = :i
                      AND s.warehouse_id = :w
                      AND s.qty > 0
                    ORDER BY lo.expiry_date ASC NULLS LAST, s.lot_id_key ASC
                    FOR UPDATE OF s
                    """
                ),
                {"i": int(item_id), "w": int(warehouse_id)},
            )
        ).all()

        if not rows:
            available = await _load_total_available_qty(session, warehouse_id=int(warehouse_id), item_id=int(item_id))
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                context={"warehouse_id": int(warehouse_id), "item_id": int(item_id), "ref": str(ref)},
                details=[
                    _shortage_detail(
                        item_id=int(item_id),
                        batch_code=None,
                        available_qty=int(available),
                        required_qty=int(remain),
                        path=f"ship_commit_direct_lot[item_id={int(item_id)}]",
                    )
                ],
                next_actions=[
                    {"action": "rescan_stock", "label": "刷新库存"},
                    {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                ],
            )

        # 贪心扣减
        for r in rows:
            if remain <= 0:
                break

            lot_id = r.lot_id
            lot_code = r.lot_code
            on_hand = int(r.qty or 0)
            if on_hand <= 0:
                continue

            take = min(remain, on_hand)
            if take <= 0:
                continue

            # ref_line：每条腿递增，避免同 ref 下多腿写同 ref_line
            ref_line = int(len(effects) + 1)

            await adjust_lot_fn(
                session=session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                lot_id=(int(lot_id) if lot_id is not None else None),
                delta=-int(take),
                reason=MovementType.SHIP,
                ref=str(ref),
                ref_line=int(ref_line),
                occurred_at=ts,
                trace_id=trace_id,
                batch_code=(str(lot_code) if lot_code is not None else None),  # 展示码
                meta={"sub_reason": "ORDER_SHIP"},
            )

            effects.append(
                {
                    "warehouse_id": int(warehouse_id),
                    "item_id": int(item_id),
                    "batch_code": (str(lot_code) if lot_code is not None else None),
                    "qty": -int(take),
                    "ref": str(ref),
                    "ref_line": int(ref_line),
                }
            )

            remain -= int(take)
            total += int(take)

        if remain > 0:
            available = await _load_total_available_qty(session, warehouse_id=int(warehouse_id), item_id=int(item_id))
            raise_problem(
                status_code=409,
                error_code="insufficient_stock",
                message="库存不足，禁止提交出库。",
                context={"warehouse_id": int(warehouse_id), "item_id": int(item_id), "ref": str(ref)},
                details=[
                    _shortage_detail(
                        item_id=int(item_id),
                        batch_code=None,
                        available_qty=int(available),
                        required_qty=int(remain),
                        path=f"ship_commit_direct_lot[item_id={int(item_id)}].remain",
                    )
                ],
                next_actions=[
                    {"action": "rescan_stock", "label": "刷新库存"},
                    {"action": "adjust_to_available", "label": "按可用库存调整数量"},
                ],
            )

    if effects:
        await enforce_three_books(session, ref=str(ref), effects=effects, at=ts)

    return {"idempotent": bool(idempotent), "applied": not bool(idempotent), "ref": str(ref), "total_qty": int(total)}
