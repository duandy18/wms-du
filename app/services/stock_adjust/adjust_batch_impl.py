# app/services/stock_adjust/adjust_batch_impl.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.lot_guard import assert_lot_belongs_to
from app.services.stock_adjust.batch_keys import norm_batch_code
from app.services.stock_adjust.date_rules import resolve_and_validate_dates_for_inbound
from app.services.stock_adjust.db_items import item_requires_batch
from app.services.stock_adjust.idempotency import idem_hit_by_lot_and_batch_key
from app.services.stock_adjust.legacy_stocks_repo import (
    apply_stock_delta,
    ensure_stock_slot_exists,
    lock_stock_slot_for_update,
)
from app.services.stock_adjust.meta import meta_bool, meta_str
from app.services.stock_adjust.stocks_lot_repo import (
    apply_stocks_lot_set_qty,
    ensure_stocks_lot_slot_exists,
    lock_stocks_lot_slot_for_update,
)


async def adjust_impl(  # noqa: C901
    *,
    session: AsyncSession,
    item_id: int,
    delta: int,
    reason: Union[str, MovementType],
    ref: str,
    ref_line: Optional[Union[int, str]] = None,
    occurred_at: Optional[datetime] = None,
    meta: Optional[Dict[str, Any]] = None,
    batch_code: Optional[str] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    warehouse_id: int,
    trace_id: Optional[str],
    lot_id: Optional[int],
    utc_now: Callable[[], datetime],
    ensure_batch_dict_fn: Callable[
        [AsyncSession, int, int, str, Optional[date], Optional[date], datetime],
        Awaitable[None],
    ],
) -> Dict[str, Any]:
    """
    legacy：batch-world 主写入口（4B）
    说明：此实现仍以 stocks 为余额槽位，并 shadow 更新 stocks_lot（历史兼容）。
    """
    reason_val = reason.value if isinstance(reason, MovementType) else str(reason)
    rl = int(ref_line) if ref_line is not None else 1
    ts = occurred_at or utc_now()

    allow_zero = meta_bool(meta, "allow_zero_delta_ledger")
    sub_reason = meta_str(meta, "sub_reason")

    if delta == 0 and not allow_zero:
        return {"idempotent": True, "applied": False}

    if delta == 0 and allow_zero and not sub_reason:
        raise ValueError("delta==0 记账必须提供 meta.sub_reason（例如 COUNT_ADJUST）")

    requires_batch = await item_requires_batch(session, item_id=int(item_id))
    bc_norm = norm_batch_code(batch_code)

    if requires_batch and not bc_norm:
        raise ValueError("批次受控商品必须指定 batch_code。")

    await assert_lot_belongs_to(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=lot_id,
    )

    production_date, expiry_date = await resolve_and_validate_dates_for_inbound(
        session=session,
        item_id=int(item_id),
        delta=int(delta),
        batch_code_norm=bc_norm,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    if await idem_hit_by_lot_and_batch_key(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code_norm=bc_norm,
        lot_id=lot_id,
        reason=reason_val,
        ref=str(ref),
        ref_line=int(rl),
    ):
        return {"idempotent": True, "applied": False}

    if delta > 0 and bc_norm is not None:
        await ensure_batch_dict_fn(
            session,
            int(warehouse_id),
            int(item_id),
            str(bc_norm),
            production_date,
            expiry_date,
            ts,
        )

    await ensure_stock_slot_exists(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code_norm=bc_norm,
    )

    stock_id, before_qty = await lock_stock_slot_for_update(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        batch_code_norm=bc_norm,
    )

    if delta == 0:
        new_qty = before_qty
    else:
        new_qty = before_qty + int(delta)
        if new_qty < 0:
            raise ValueError(f"insufficient stock: before={before_qty}, delta={delta}")

    # audit-consistency：记账必须通过白名单入口（stock_service_adjust.write_ledger_infra）
    # 这里必须用 lazy import，避免 stock_service_adjust <-> stock_adjust 循环导入
    from app.services.stock_service_adjust import write_ledger_infra  # noqa: WPS433

    await write_ledger_infra(
        session=session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=bc_norm,
        reason=reason_val,
        sub_reason=sub_reason,
        delta=int(delta),
        after_qty=new_qty,
        ref=str(ref),
        ref_line=int(rl),
        occurred_at=ts,
        trace_id=trace_id,
        production_date=production_date,
        expiry_date=expiry_date,
        lot_id=lot_id,
    )

    if delta != 0:
        await apply_stock_delta(session, stock_id=int(stock_id), delta=int(delta))

        # shadow: keep stocks_lot updated during 4B
        await ensure_stocks_lot_slot_exists(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_id=lot_id,
        )
        lot_slot_id, lot_before = await lock_stocks_lot_slot_for_update(
            session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_id=lot_id,
        )
        await apply_stocks_lot_set_qty(session, slot_id=int(lot_slot_id), new_qty=int(lot_before + int(delta)))

    meta_out: Dict[str, Any] = dict(meta or {})
    if trace_id:
        meta_out.setdefault("trace_id", trace_id)

    return {
        "stock_id": int(stock_id),
        "before": int(before_qty),
        "delta": int(delta),
        "after": int(new_qty),
        "reason": str(reason_val),
        "ref": str(ref),
        "ref_line": int(rl),
        "meta": meta_out,
        "occurred_at": ts.isoformat(),
        "production_date": production_date,
        "expiry_date": expiry_date,
    }
