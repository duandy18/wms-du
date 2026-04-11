# app/wms/reconciliation/services/receive_handler.py
from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.stock.services.stock_adjust.db_items import item_requires_batch
from app.wms.stock.services.stock_service import StockService
from app.wms.shared.services.expiry_resolver import normalize_batch_dates_for_item


async def handle_receive(
    session: AsyncSession,
    *,
    item_id: int,
    warehouse_id: int,
    qty: int,
    ref: str,
    batch_code: str | None,
    production_date: date | None = None,
    expiry_date: date | None = None,
    trace_id: str | None = None,
) -> dict:
    """
    入库入口（receive）：

    - REQUIRED/NONE 的 batch_code 裁决仍由 StockService.adjust(合同闸门)负责；
    - 但对 requires_batch=False（expiry_policy=NONE），入口层必须把 batch_code 投影为 None，
      否则会触发合同 batch_forbidden；
    - 对 requires_batch=True，入口层必须先把用户输入日期归一成 resolved_production_date /
      resolved_expiry_date，再交给下游 lot / ledger 写入口。
    """
    if qty <= 0:
        raise ValueError("Receive quantity must be positive.")
    if warehouse_id is None or int(warehouse_id) <= 0:
        raise ValueError("入库操作必须明确 warehouse_id。")

    requires_batch = await item_requires_batch(session, item_id=int(item_id))

    bc_norm = (str(batch_code).strip() if batch_code is not None else None) or None

    # NONE 商品必须把 batch_code 投影为 None
    if not requires_batch:
        bc_norm = None
        resolved_production_date = None
        resolved_expiry_date = None
    else:
        if production_date is None and expiry_date is None:
            raise ValueError("入库操作必须提供 production_date 或 expiry_date（至少其一）。")

        resolved_production_date, resolved_expiry_date, _resolution_mode = await normalize_batch_dates_for_item(
            session,
            item_id=item_id,
            production_date=production_date,
            expiry_date=expiry_date,
        )

        # 当前 REQUIRED lot 身份仍依赖 production_date
        if resolved_production_date is None:
            raise ValueError("批次受控商品必须提供 production_date，或提供可结合保质期反推出 production_date 的 expiry_date。")

        # lot canonical 现在要求 expiry_date 一并形成
        if resolved_expiry_date is None:
            raise ValueError("未提供到期日期，且商品未配置可用于推算的保质期，无法形成 canonical expiry_date。")

    res = await StockService().adjust(
        session=session,
        item_id=item_id,
        warehouse_id=warehouse_id,
        delta=int(qty),
        reason=MovementType.INBOUND,
        ref=ref,
        batch_code=bc_norm,
        production_date=resolved_production_date if requires_batch else None,
        expiry_date=resolved_expiry_date if requires_batch else None,
        trace_id=trace_id,
    )

    applied = bool(res.get("applied", True))
    idempotent = bool(res.get("idempotent", False)) or (not applied)

    out = {
        "qty": int(qty),
        "batch_code": bc_norm,
        "warehouse_id": int(warehouse_id),
        "idempotent": idempotent,
        "applied": applied,
    }

    for k in (
        "lot_id",
        "before",
        "after",
        "delta",
        "reason",
        "ref",
        "ref_line",
        "occurred_at",
        "production_date",
        "expiry_date",
    ):
        if k in res:
            out[k] = res.get(k)

    return out
