from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.inbound.models.inbound_event import InboundEventLine, WmsEvent
from app.wms.inventory_adjustment.inbound_reversal.contracts.inbound_reversal import (
    InboundReversalIn,
    InboundReversalOut,
    InboundReversalRowOut,
)
from app.wms.inventory_adjustment.inbound_reversal.repos.inbound_reversal_repo import (
    find_committed_inbound_reversal,
    get_inbound_event_for_reversal,
    list_inbound_event_lines_for_reversal,
    mark_inbound_event_superseded,
)
from app.wms.stock.services.stock_service import StockService

UTC = timezone.utc


def _new_trace_id() -> str:
    return f"IN-REV-{uuid4().hex[:20]}"


def _new_event_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"IER-{stamp}-{uuid4().hex[:8].upper()}"


def _norm_text(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


async def reverse_inbound_event(
    session: AsyncSession,
    *,
    event_id: int,
    payload: InboundReversalIn,
    user_id: int | None = None,
) -> InboundReversalOut:
    existing = await find_committed_inbound_reversal(
        session,
        target_event_id=int(event_id),
    )
    existing = await find_committed_inbound_reversal(
        session,
        target_event_id=int(event_id),
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"inbound_event_already_reversed:{int(existing['id'])}",
        )

    original = await get_inbound_event_for_reversal(session, event_id=int(event_id))
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"inbound_event_already_reversed:{int(existing['id'])}",
        )

    source_lines = await list_inbound_event_lines_for_reversal(
        session,
        event_id=int(original["event_id"]),
    )

    occurred_at = payload.occurred_at
    trace_id = _new_trace_id()
    event_no = _new_event_no()

    event = WmsEvent(
        event_no=str(event_no),
        event_type="INBOUND",
        warehouse_id=int(original["warehouse_id"]),
        source_type=str(original["source_type"]),
        source_ref=_norm_text(original["source_ref"]),
        occurred_at=occurred_at,
        trace_id=str(trace_id),
        event_kind="REVERSAL",
        target_event_id=int(original["event_id"]),
        status="COMMITTED",
        created_by=int(user_id) if user_id is not None else None,
        remark=_norm_text(payload.remark) or f"reversal of {original['event_no']}",
    )
    session.add(event)
    await session.flush()

    stock = StockService()
    rows: list[InboundReversalRowOut] = []

    for src in source_lines:
        line_no = int(src["line_no"])
        item_id = int(src["item_id"])
        lot_id = src["lot_id"]
        qty_base = int(src["qty_base"])

        if lot_id is None:
            raise HTTPException(
                status_code=409,
                detail=f"inbound_event_line_missing_lot:{line_no}",
            )
        if qty_base <= 0:
            raise HTTPException(
                status_code=409,
                detail=f"inbound_event_line_invalid_qty_base:{line_no}",
            )

        event_line = InboundEventLine(
            event_id=int(event.id),
            line_no=line_no,
            item_id=item_id,
            actual_uom_id=int(src["actual_uom_id"]),
            barcode_input=_norm_text(src["barcode_input"]),
            actual_qty_input=int(src["actual_qty_input"]),
            actual_ratio_to_base_snapshot=int(src["actual_ratio_to_base_snapshot"]),
            qty_base=qty_base,
            lot_code_input=_norm_text(src["lot_code_input"]),
            production_date=src["production_date"],
            expiry_date=src["expiry_date"],
            lot_id=int(lot_id),
            po_line_id=(int(src["po_line_id"]) if src["po_line_id"] is not None else None),
            remark=_norm_text(src["remark"]),
        )
        session.add(event_line)
        await session.flush()

        await stock.adjust_lot(
            session=session,
            item_id=item_id,
            warehouse_id=int(original["warehouse_id"]),
            lot_id=int(lot_id),
            delta=-qty_base,
            reason=MovementType.ADJUSTMENT,
            ref=str(event.event_no),
            ref_line=line_no,
            occurred_at=occurred_at,
            batch_code=None,
            production_date=None,
            expiry_date=None,
            trace_id=str(trace_id),
            meta={
                "sub_reason": "INBOUND_REVERSAL",
                "event_id": int(event.id),
                "target_event_id": int(original["event_id"]),
                "source_type": str(original["source_type"]),
                "source_ref": _norm_text(original["source_ref"]),
                "remark": _norm_text(event.remark),
            },
            shadow_write_stocks=False,
        )

        rows.append(
            InboundReversalRowOut(
                line_no=line_no,
                item_id=item_id,
                lot_id=int(lot_id),
                qty_base=qty_base,
            )
        )

    await mark_inbound_event_superseded(
        session,
        event_id=int(original["event_id"]),
    )

    return InboundReversalOut(
        ok=True,
        event_id=int(event.id),
        event_no=str(event.event_no),
        trace_id=str(trace_id),
        target_event_id=int(original["event_id"]),
        warehouse_id=int(original["warehouse_id"]),
        source_type=str(original["source_type"]),
        source_ref=_norm_text(original["source_ref"]),
        occurred_at=occurred_at,
        remark=_norm_text(event.remark),
        rows=rows,
    )


__all__ = [
    "reverse_inbound_event",
]
