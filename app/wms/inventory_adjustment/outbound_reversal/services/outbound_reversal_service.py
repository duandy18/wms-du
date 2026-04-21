from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.inbound.models.inbound_event import WmsEvent
from app.wms.inventory_adjustment.outbound_reversal.contracts.outbound_reversal import (
    OutboundReversalIn,
    OutboundReversalOut,
    OutboundReversalRowOut,
)
from app.wms.inventory_adjustment.outbound_reversal.repos.outbound_reversal_repo import (
    find_committed_outbound_reversal,
    get_outbound_event_for_reversal,
    list_outbound_event_lines_for_reversal,
    mark_outbound_event_superseded,
)
from app.wms.outbound.models.outbound_event import OutboundEventLine
from app.wms.stock.services.stock_service import StockService

UTC = timezone.utc


def _new_trace_id() -> str:
    return f"OUT-REV-{uuid4().hex[:20]}"


def _new_event_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"OER-{stamp}-{uuid4().hex[:8].upper()}"


def _norm_text(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


async def reverse_outbound_event(
    session: AsyncSession,
    *,
    event_id: int,
    payload: OutboundReversalIn,
    user_id: int | None = None,
) -> OutboundReversalOut:
    existing = await find_committed_outbound_reversal(
        session,
        target_event_id=int(event_id),
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"outbound_event_already_reversed:{int(existing['id'])}",
        )

    original = await get_outbound_event_for_reversal(session, event_id=int(event_id))
    source_lines = await list_outbound_event_lines_for_reversal(
        session,
        event_id=int(original["event_id"]),
    )

    occurred_at = payload.occurred_at
    trace_id = _new_trace_id()
    event_no = _new_event_no()

    event = WmsEvent(
        event_no=str(event_no),
        event_type="OUTBOUND",
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
    rows: list[OutboundReversalRowOut] = []

    for src in source_lines:
        ref_line = int(src["ref_line"])
        item_id = int(src["item_id"])
        lot_id = src["lot_id"]
        qty_outbound = int(src["qty_outbound"])

        if lot_id is None:
            raise HTTPException(
                status_code=409,
                detail=f"outbound_event_line_missing_lot:{ref_line}",
            )
        if qty_outbound <= 0:
            raise HTTPException(
                status_code=409,
                detail=f"outbound_event_line_invalid_qty:{ref_line}",
            )

        event_line = OutboundEventLine(
            event_id=int(event.id),
            ref_line=ref_line,
            item_id=item_id,
            qty_outbound=qty_outbound,
            lot_id=int(lot_id),
            lot_code_snapshot=_norm_text(src["lot_code_snapshot"]),
            order_line_id=(int(src["order_line_id"]) if src["order_line_id"] is not None else None),
            manual_doc_line_id=(int(src["manual_doc_line_id"]) if src["manual_doc_line_id"] is not None else None),
            item_name_snapshot=_norm_text(src["item_name_snapshot"]),
            item_sku_snapshot=_norm_text(src["item_sku_snapshot"]),
            item_spec_snapshot=_norm_text(src["item_spec_snapshot"]),
            remark=_norm_text(src["remark"]),
        )
        session.add(event_line)
        await session.flush()

        await stock.adjust_lot(
            session=session,
            item_id=item_id,
            warehouse_id=int(original["warehouse_id"]),
            lot_id=int(lot_id),
            delta=qty_outbound,
            reason=MovementType.ADJUSTMENT,
            ref=str(event.event_no),
            ref_line=ref_line,
            occurred_at=occurred_at,
            batch_code=None,
            production_date=None,
            expiry_date=None,
            trace_id=str(trace_id),
            meta={
                "sub_reason": "OUTBOUND_REVERSAL",
                "event_id": int(event.id),
                "target_event_id": int(original["event_id"]),
                "source_type": str(original["source_type"]),
                "source_ref": _norm_text(original["source_ref"]),
                "remark": _norm_text(event.remark),
            },
            shadow_write_stocks=False,
        )

        rows.append(
            OutboundReversalRowOut(
                ref_line=ref_line,
                item_id=item_id,
                lot_id=int(lot_id),
                qty_outbound=qty_outbound,
            )
        )

    await mark_outbound_event_superseded(
        session,
        event_id=int(original["event_id"]),
    )

    return OutboundReversalOut(
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
    "reverse_outbound_event",
]
