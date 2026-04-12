# app/wms/procurement/services/inbound_receipt_confirm.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import raise_problem
from app.procurement.contracts.inbound_receipt import InboundReceiptOut
from app.procurement.contracts.inbound_receipt_confirm import (
    InboundReceiptConfirmLedgerRef,
    InboundReceiptConfirmOut,
)
from app.procurement.repos.inbound_receipt_confirm_repo import (
    load_items_by_ids,
    load_receipt_for_update,
)
from app.procurement.services.inbound_receipt_explain import explain_receipt
from app.procurement.services.inbound_atomic_adapter import apply_receipt_via_atomic_inbound
from app.wms.shared.services.expiry_resolver import normalize_batch_dates_for_item

UTC = timezone.utc


async def confirm_receipt(
    *,
    session: AsyncSession,
    receipt_id: int,
    user_id: int | None = None,
) -> InboundReceiptConfirmOut:
    _ = user_id

    receipt = await load_receipt_for_update(session, receipt_id=receipt_id)
    status = str(getattr(receipt, "status", "") or "").upper()

    if status == "CONFIRMED":
        return InboundReceiptConfirmOut(
            receipt=InboundReceiptOut.model_validate(receipt),
            ledger_written=0,
            ledger_refs=[],
        )

    if status != "DRAFT":
        raise_problem(
            status_code=409,
            error_code="RECEIPT_STATE_CONFLICT",
            message="收货单状态冲突，无法确认。",
        )

    exp = await explain_receipt(session=session, receipt=receipt)
    if not exp.confirmable:
        raise_problem(
            status_code=422,
            error_code="RECEIPT_NOT_CONFIRMABLE",
            message="收货单不满足确认条件。",
            details=[e.model_dump() for e in exp.blocking_errors],
        )

    ref = str(getattr(receipt, "ref"))
    occurred_at = getattr(receipt, "occurred_at", None) or datetime.now(UTC)
    warehouse_id = int(getattr(receipt, "warehouse_id"))

    receipt_lines = list(receipt.lines or [])
    item_ids = [int(getattr(rl, "item_id")) for rl in receipt_lines]
    item_map = await load_items_by_ids(session, item_ids=item_ids)

    atomic_lines: list[dict[str, object]] = []

    for idx, rl in enumerate(receipt_lines, start=1):
        item_id = int(getattr(rl, "item_id"))
        qty_delta = int(getattr(rl, "qty_base", 0) or 0)

        item = item_map.get(item_id)
        if item is None:
            raise_problem(
                status_code=422,
                error_code="ITEM_NOT_FOUND",
                message=f"商品不存在：item_id={item_id}",
            )

        raw_production_date = getattr(rl, "production_date", None)
        raw_expiry_date = getattr(rl, "expiry_date", None)

        resolved_production_date, resolved_expiry_date, _resolution_mode = await normalize_batch_dates_for_item(
            session,
            item_id=item_id,
            production_date=raw_production_date,
            expiry_date=raw_expiry_date,
        )

        item_expiry_policy = str(getattr(item, "expiry_policy", "NONE") or "NONE").upper()
        if item_expiry_policy == "REQUIRED":
            if resolved_production_date is None:
                raise_problem(
                    status_code=422,
                    error_code="RECEIPT_LINE_DATE_UNRESOLVED",
                    message="批次受控商品必须提供 production_date，或提供可结合保质期反推出 production_date 的 expiry_date。",
                    details=[{"line_no": int(getattr(rl, "line_no", idx)), "item_id": int(item_id)}],
                )
            if resolved_expiry_date is None:
                raise_problem(
                    status_code=422,
                    error_code="RECEIPT_LINE_DATE_UNRESOLVED",
                    message="未提供到期日期，且商品未配置可用于推算的保质期，无法形成 canonical expiry_date。",
                    details=[{"line_no": int(getattr(rl, "line_no", idx)), "item_id": int(item_id)}],
                )

        # 把 line 上的日期更新成 canonical，避免确认后仍残留原始输入语义
        rl.production_date = resolved_production_date
        rl.expiry_date = resolved_expiry_date

        atomic_lines.append(
            {
                "item_id": int(item_id),
                "qty": int(qty_delta),
                "ref_line": int(idx),
                "lot_code": getattr(rl, "lot_code_input", None),
                "production_date": resolved_production_date,
                "expiry_date": resolved_expiry_date,
            }
        )

    # 整张 receipt 一次 atomic inbound => 一张 receipt 一个统一事件头
    atomic_res = await apply_receipt_via_atomic_inbound(
        session,
        warehouse_id=warehouse_id,
        receipt_ref=ref,
        occurred_at=occurred_at,
        remark=getattr(receipt, "remark", None),
        lines=atomic_lines,
    )

    out_rows = list(atomic_res.get("rows") or [])
    if len(out_rows) != len(receipt_lines):
        raise_problem(
            status_code=500,
            error_code="RECEIPT_CONFIRM_ROW_MISMATCH",
            message="确认收货后返回的结果行数与输入行数不一致。",
            details=[
                {
                    "expected_rows": len(receipt_lines),
                    "actual_rows": len(out_rows),
                    "receipt_id": int(receipt_id),
                    "receipt_ref": ref,
                }
            ],
        )

    ledger_refs: List[InboundReceiptConfirmLedgerRef] = []

    for idx, rl in enumerate(receipt_lines, start=1):
        item_id = int(getattr(rl, "item_id"))
        qty_delta = int(getattr(rl, "qty_base", 0) or 0)

        row = out_rows[idx - 1]
        if getattr(row, "lot_id", None) is not None:
            rl.lot_id = int(row.lot_id)

        if getattr(rl, "receipt_status_snapshot", None) != "CONFIRMED":
            rl.receipt_status_snapshot = "CONFIRMED"

        ledger_refs.append(
            InboundReceiptConfirmLedgerRef(
                source_line_key=f"LINE:{getattr(rl, 'line_no', idx)}",
                ref=ref,
                ref_line=idx,
                item_id=item_id,
                qty_delta=qty_delta,
                event_id=int(atomic_res["event_id"]) if atomic_res.get("event_id") is not None else None,
                event_no=str(atomic_res["event_no"]) if atomic_res.get("event_no") else None,
                trace_id=str(atomic_res["trace_id"]) if atomic_res.get("trace_id") else None,
                idempotent=None,
                applied=True,
            )
        )

    receipt.status = "CONFIRMED"
    await session.flush()

    return InboundReceiptConfirmOut(
        receipt=InboundReceiptOut.model_validate(receipt),
        ledger_written=len(ledger_refs),
        ledger_refs=ledger_refs,
    )
