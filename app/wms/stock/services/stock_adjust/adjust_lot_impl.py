# app/wms/stock/services/stock_adjust/adjust_lot_impl.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Dict, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.stock.services.lot_guard import assert_lot_belongs_to
from app.wms.stock.services.stock_adjust.batch_keys import norm_batch_code
from app.wms.stock.services.stock_adjust.date_rules import resolve_and_validate_dates_for_inbound
from app.wms.stock.services.stock_adjust.db_items import item_requires_batch
from app.wms.stock.services.stock_adjust.idempotency import idem_hit_by_lot_and_batch_key
from app.wms.stock.services.stock_adjust.lot_code_repo import load_lot_code_for_lot_id
from app.wms.stock.services.stock_adjust.meta import meta_bool, meta_str


def _meta_int(meta: Optional[Dict[str, Any]], key: str) -> Optional[int]:
    if not meta:
        return None
    value = meta.get(key)
    if value is None:
        return None
    try:
        iv = int(value)
    except Exception:
        raise ValueError(f"meta.{key} must be int") from None
    return iv if iv > 0 else None


async def adjust_lot_impl(
    *,
    session: AsyncSession,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
    delta: int,
    reason: Union[str, MovementType],
    ref: str,
    ref_line: Optional[Union[int, str]] = None,
    occurred_at: Optional[datetime] = None,
    meta: Optional[Dict[str, Any]] = None,
    batch_code: Optional[str] = None,
    production_date: Optional[date] = None,
    expiry_date: Optional[date] = None,
    trace_id: Optional[str],
    utc_now: Callable[[], datetime],
) -> Dict[str, Any]:
    """
    Phase M-2 终态：lot-world 主写入口（结构封板）

    - 余额：写 stocks_lot（按 lot_id）
    - 台账：写 stock_ledger（必须带 lot_id）
    - 幂等：按 (warehouse_id, item_id, lot_id, reason, ref, ref_line) 命中
    当前补充：
    - 若 meta.event_id 存在，则继续向下传到 stock_ledger.event_id
    """
    reason_val = reason.value if isinstance(reason, MovementType) else str(reason)
    rl = int(ref_line) if ref_line is not None else 1
    ts = occurred_at or utc_now()

    allow_zero = meta_bool(meta, "allow_zero_delta_ledger")
    sub_reason = meta_str(meta, "sub_reason")
    event_id = _meta_int(meta, "event_id")

    if delta == 0 and not allow_zero:
        return {"idempotent": True, "applied": False}

    if delta == 0 and allow_zero and not sub_reason:
        raise ValueError("delta==0 记账必须提供 meta.sub_reason（例如 COUNT_ADJUST）")

    if lot_id is None:
        raise ValueError("lot_id is required in lot-only world.")

    requires_batch = await item_requires_batch(session, item_id=int(item_id))
    bc_norm = norm_batch_code(batch_code)

    # 终态：批次受控商品允许 batch_code 为空（展示码），但 lot_id 必须存在
    if requires_batch and not lot_id:
        raise ValueError("批次受控商品必须指定 lot_id。")

    await assert_lot_belongs_to(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=int(lot_id),
    )

    production_date, expiry_date = await resolve_and_validate_dates_for_inbound(
        session=session,
        item_id=int(item_id),
        delta=int(delta),
        batch_code_norm=bc_norm,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    # 幂等：lot-only
    if await idem_hit_by_lot_and_batch_key(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code_norm=bc_norm,
        lot_id=int(lot_id),
        reason=reason_val,
        ref=str(ref),
        ref_line=int(rl),
    ):
        return {"idempotent": True, "applied": False}

    from app.wms.stock.services.stock_adjust.stocks_lot_repo import (
        apply_stocks_lot_set_qty,
        ensure_stocks_lot_slot_exists,
        lock_stocks_lot_slot_for_update,
    )

    await ensure_stocks_lot_slot_exists(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
    )

    lot_slot_id, before_qty = await lock_stocks_lot_slot_for_update(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=int(lot_id),
    )

    if delta == 0:
        new_qty = before_qty
    else:
        new_qty = before_qty + int(delta)
        if new_qty < 0:
            raise ValueError(f"insufficient stock(lot): before={before_qty}, delta={delta}")

    # 展示码：优先用 lot_id 对应的 lots.lot_code（若存在）
    if not bc_norm:
        bc_norm = await load_lot_code_for_lot_id(session, lot_id=int(lot_id))

    # audit-consistency：记账必须通过白名单入口（stock_service_adjust.write_ledger_infra）
    # 这里必须用 lazy import，避免 stock_service_adjust <-> stock_adjust 循环导入
    from app.wms.ledger.services.stock_service_adjust import write_ledger_infra  # noqa: WPS433

    await write_ledger_infra(
        session=session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        batch_code=bc_norm,
        reason=reason_val,
        sub_reason=sub_reason,
        delta=int(delta),
        after_qty=int(new_qty),
        ref=str(ref),
        ref_line=int(rl),
        occurred_at=ts,
        trace_id=trace_id,
        event_id=event_id,
        production_date=production_date,
        expiry_date=expiry_date,
        lot_id=int(lot_id),
    )

    if delta != 0:
        await apply_stocks_lot_set_qty(session, slot_id=int(lot_slot_id), new_qty=int(new_qty))

    meta_out: Dict[str, Any] = dict(meta or {})
    if trace_id:
        meta_out.setdefault("trace_id", trace_id)
    if event_id is not None:
        meta_out.setdefault("event_id", event_id)

    return {
        "lot_id": int(lot_id),
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
