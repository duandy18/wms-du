from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.wms.inbound.models.inbound_event import InboundEventLine, WmsEvent
from app.wms.inventory_adjustment.count.services.count_freeze_guard_service import (
    ensure_warehouse_not_frozen,
)
from app.wms.inventory_adjustment.inbound_reversal.contracts.inbound_reversal import (
    InboundReversalIn,
    InboundReversalOut,
    InboundReversalRowOut,
)
from app.wms.inventory_adjustment.inbound_reversal.contracts.inbound_reversal_read import (
    InboundReversalDetailLineOut,
    InboundReversalDetailOut,
    InboundReversalOptionOut,
    InboundReversalOptionsOut,
)
from app.wms.inventory_adjustment.inbound_reversal.repos.inbound_reversal_repo import (
    find_committed_inbound_reversal,
    get_inbound_event_for_reversal,
    get_inbound_event_header,
    list_inbound_event_lines_for_reversal,
    list_inbound_reversal_options,
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


def _freeze_reason(detail: object) -> str:
    if isinstance(detail, dict):
        error_code = str(detail.get("error_code") or "").strip()
        if error_code == "count_doc_frozen_for_warehouse":
            return "该仓当前存在冻结中的盘点单，禁止执行入库冲回"
    return "该原入库事件当前不允许冲回"


async def _non_reversible_reason(
    session: AsyncSession,
    *,
    header: dict[str, object],
) -> str | None:
    if str(header["event_kind"]) != "COMMIT":
        return f"当前事件类型为 {header['event_kind']}，不允许冲回"

    if str(header["status"]) != "COMMITTED":
        return f"当前状态为 {header['status']}，不允许冲回"

    existing = await find_committed_inbound_reversal(
        session,
        target_event_id=int(header["event_id"]),
    )
    if existing is not None:
        return f"该原入库事件已被冲回：{existing['event_no']}"

    try:
        await ensure_warehouse_not_frozen(
            session,
            warehouse_id=int(header["warehouse_id"]),
        )
    except HTTPException as exc:
        return _freeze_reason(exc.detail)

    return None


async def list_reversible_inbound_events(
    session: AsyncSession,
    *,
    days: int,
    limit: int,
    source_type: str | None,
) -> InboundReversalOptionsOut:
    rows = await list_inbound_reversal_options(
        session,
        days=days,
        limit=limit,
        source_type=source_type,
    )

    items: list[InboundReversalOptionOut] = []
    for row in rows:
        reason = await _non_reversible_reason(session, header=row)
        items.append(
            InboundReversalOptionOut(
                event_id=int(row["event_id"]),
                event_no=str(row["event_no"]),
                warehouse_id=int(row["warehouse_id"]),
                source_type=str(row["source_type"]),
                source_ref=_norm_text(row["source_ref"]),
                occurred_at=row["occurred_at"],
                committed_at=row["committed_at"],
                remark=_norm_text(row["remark"]),
                line_count=int(row["line_count"] or 0),
                qty_base_total=int(row["qty_base_total"] or 0),
                reversible=reason is None,
                non_reversible_reason=reason,
            )
        )

    return InboundReversalOptionsOut(items=items)


async def get_reversible_inbound_event_detail(
    session: AsyncSession,
    *,
    event_id: int,
) -> InboundReversalDetailOut:
    header = await get_inbound_event_header(session, event_id=int(event_id))
    if header is None:
        raise HTTPException(status_code=404, detail=f"inbound_event_not_found:{int(event_id)}")

    line_rows = await list_inbound_event_lines_for_reversal(
        session,
        event_id=int(event_id),
        require_nonempty=False,
    )

    reason = await _non_reversible_reason(session, header=header)
    if not line_rows and reason is None:
        reason = "该原入库事件没有可冲回行"

    lines = [
        InboundReversalDetailLineOut(
            line_no=int(r["line_no"]),
            item_id=int(r["item_id"]),
            item_name_snapshot=_norm_text(r["item_name_snapshot"]),
            item_spec_snapshot=_norm_text(r["item_spec_snapshot"]),
            actual_uom_id=int(r["actual_uom_id"]),
            actual_uom_name_snapshot=_norm_text(r["actual_uom_name_snapshot"]),
            actual_qty_input=int(r["actual_qty_input"]),
            actual_ratio_to_base_snapshot=int(r["actual_ratio_to_base_snapshot"]),
            qty_base=int(r["qty_base"]),
            lot_id=(int(r["lot_id"]) if r["lot_id"] is not None else None),
            lot_code_input=_norm_text(r["lot_code_input"]),
            production_date=r["production_date"],
            expiry_date=r["expiry_date"],
            remark=_norm_text(r["remark"]),
        )
        for r in line_rows
    ]

    return InboundReversalDetailOut(
        event_id=int(header["event_id"]),
        event_no=str(header["event_no"]),
        warehouse_id=int(header["warehouse_id"]),
        source_type=str(header["source_type"]),
        source_ref=_norm_text(header["source_ref"]),
        occurred_at=header["occurred_at"],
        committed_at=header["committed_at"],
        status=str(header["status"]),
        remark=_norm_text(header["remark"]),
        line_count=int(header["line_count"] or 0),
        qty_base_total=int(header["qty_base_total"] or 0),
        reversible=reason is None,
        non_reversible_reason=reason,
        lines=lines,
    )


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
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"inbound_event_already_reversed:{int(existing['id'])}",
        )

    original = await get_inbound_event_for_reversal(session, event_id=int(event_id))
    source_lines = await list_inbound_event_lines_for_reversal(
        session,
        event_id=int(original["event_id"]),
        require_nonempty=True,
    )

    await ensure_warehouse_not_frozen(
        session,
        warehouse_id=int(original["warehouse_id"]),
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
            item_name_snapshot=_norm_text(src["item_name_snapshot"]),
            item_spec_snapshot=_norm_text(src["item_spec_snapshot"]),
            actual_uom_id=int(src["actual_uom_id"]),
            actual_uom_name_snapshot=_norm_text(src["actual_uom_name_snapshot"]),
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
                "operator_name_snapshot": _norm_text(payload.operator_name_snapshot),
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
        operator_name_snapshot=str(payload.operator_name_snapshot),
        remark=_norm_text(event.remark),
        rows=rows,
    )


__all__ = [
    "list_reversible_inbound_events",
    "get_reversible_inbound_event_detail",
    "reverse_inbound_event",
]
