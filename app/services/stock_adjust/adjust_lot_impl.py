# app/services/stock_adjust/adjust_lot_impl.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Dict, Optional, Union

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
from app.services.stock_adjust.lot_code_repo import load_lot_code_for_lot_id
from app.services.stock_adjust.meta import meta_bool, meta_str
from app.services.stock_adjust.stocks_lot_repo import (
    apply_stocks_lot_set_qty,
    ensure_stocks_lot_slot_exists,
    lock_stocks_lot_slot_for_update,
)


async def adjust_lot_impl(
    *,
    session: AsyncSession,
    item_id: int,
    warehouse_id: int,
    lot_id: Optional[int],
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
    shadow_write_stocks: bool = False,
) -> Dict[str, Any]:
    """
    Phase 4C：lot-world 主写入口

    - 余额：写 stocks_lot（按 lot_id_key）
    - 台账：写 stock_ledger（必须带 lot_id，使 lot_id_key 生效）
    - stocks：可选 shadow 写入（便于回滚/对账）

    Phase 4D 第一步：shadow_write_stocks 默认关闭（False）。
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

    # 4C 规则：效期商品允许通过 lot_id 表达，不强制 batch_code（展示码可为空）
    if requires_batch and (lot_id is None) and not bc_norm:
        raise ValueError("批次受控商品必须指定 lot_id 或 batch_code。")

    await assert_lot_belongs_to(
        session,
        warehouse_id=int(warehouse_id),
        item_id=int(item_id),
        lot_id=lot_id,
    )

    # 为了保持现有审计契约：如果显式传了 batch_code（lot_code），沿用 inbound 的日期解析规则
    production_date, expiry_date = await resolve_and_validate_dates_for_inbound(
        session=session,
        item_id=int(item_id),
        delta=int(delta),
        batch_code_norm=bc_norm,
        production_date=production_date,
        expiry_date=expiry_date,
    )

    # 幂等：仍以 (warehouse,item,lot_id_key,batch_code_key,reason,ref,ref_line) 命中
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

    await ensure_stocks_lot_slot_exists(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=lot_id,
    )

    lot_slot_id, before_qty = await lock_stocks_lot_slot_for_update(
        session,
        item_id=int(item_id),
        warehouse_id=int(warehouse_id),
        lot_id=lot_id,
    )

    if delta == 0:
        new_qty = before_qty
    else:
        new_qty = before_qty + int(delta)
        if new_qty < 0:
            raise ValueError(f"insufficient stock(lot): before={before_qty}, delta={delta}")

    # 展示码：优先用 lot_id 对应的 lots.lot_code（若存在）
    if lot_id is not None and not bc_norm:
        bc_norm = await load_lot_code_for_lot_id(session, lot_id=lot_id)

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
        after_qty=int(new_qty),
        ref=str(ref),
        ref_line=int(rl),
        occurred_at=ts,
        trace_id=trace_id,
        production_date=production_date,
        expiry_date=expiry_date,
        lot_id=lot_id,
    )

    if delta != 0:
        await apply_stocks_lot_set_qty(session, slot_id=int(lot_slot_id), new_qty=int(new_qty))

        if shadow_write_stocks:
            # 影子写 stocks（按 batch_code 槽位）；若 batch_code 为空，则落入 NULL 槽位
            await ensure_stock_slot_exists(
                session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                batch_code_norm=bc_norm,
            )
            stock_id, _before = await lock_stock_slot_for_update(
                session,
                item_id=int(item_id),
                warehouse_id=int(warehouse_id),
                batch_code_norm=bc_norm,
            )
            await apply_stock_delta(session, stock_id=int(stock_id), delta=int(delta))

    meta_out: Dict[str, Any] = dict(meta or {})
    if trace_id:
        meta_out.setdefault("trace_id", trace_id)

    return {
        "lot_id": lot_id,
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
