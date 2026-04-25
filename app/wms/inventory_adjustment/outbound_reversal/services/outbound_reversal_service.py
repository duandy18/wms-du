from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.shared.enums import MovementType
from app.wms.inbound.models.inbound_event import WmsEvent
from app.wms.inventory_adjustment.count.services.count_freeze_guard_service import (
    ensure_warehouse_not_frozen,
)
from app.wms.inventory_adjustment.outbound_reversal.contracts.outbound_reversal import (
    OutboundReversalDetailLineOut,
    OutboundReversalDetailOut,
    OutboundReversalIn,
    OutboundReversalOptionOut,
    OutboundReversalOptionsOut,
    OutboundReversalOut,
    OutboundReversalRowOut,
)
from app.wms.inventory_adjustment.outbound_reversal.repos.outbound_reversal_repo import (
    find_committed_outbound_reversal,
    get_outbound_event_for_reversal,
    get_outbound_reversal_detail_header,
    list_outbound_event_lines_for_reversal,
    list_outbound_reversal_option_rows,
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


async def _freeze_non_reversible_reason(
    session: AsyncSession,
    *,
    warehouse_id: int,
) -> str | None:
    try:
        await ensure_warehouse_not_frozen(
            session,
            warehouse_id=int(warehouse_id),
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        detail = exc.detail
        if isinstance(detail, dict) and detail.get("error_code") == "count_doc_frozen_for_warehouse":
            return "该仓当前存在冻结中的盘点单，禁止执行出库冲回"
        return str(detail)
    return None


async def _non_reversible_reason(
    session: AsyncSession,
    row: dict[str, object],
) -> str | None:
    if str(row["event_kind"]) != "COMMIT":
        return f"不是原出库提交事件，不能冲回：{row['event_kind']}"

    status = str(row["status"])
    if status == "SUPERSEDED":
        return "原出库事件已被冲回"
    if status != "COMMITTED":
        return f"原出库事件状态不可冲回：{status}"

    if row.get("reversal_event_id") is not None:
        return f"原出库事件已被冲回：{int(row['reversal_event_id'])}"

    if int(row.get("line_count") or 0) <= 0:
        return "原出库事件没有行明细，不能冲回"

    return await _freeze_non_reversible_reason(
        session,
        warehouse_id=int(row["warehouse_id"]),
    )


async def list_outbound_reversal_options(
    session: AsyncSession,
    *,
    days: int = 7,
    limit: int = 100,
    source_type: str | None = None,
) -> OutboundReversalOptionsOut:
    rows = await list_outbound_reversal_option_rows(
        session,
        days=int(days),
        limit=int(limit),
        source_type=_norm_text(source_type),
    )

    items: list[OutboundReversalOptionOut] = []
    for row in rows:
        reason = await _non_reversible_reason(session, row)
        items.append(
            OutboundReversalOptionOut(
                event_id=int(row["event_id"]),
                event_no=str(row["event_no"]),
                warehouse_id=int(row["warehouse_id"]),
                source_type=str(row["source_type"]),
                source_ref=_norm_text(row["source_ref"]),
                occurred_at=row["occurred_at"],
                committed_at=row["committed_at"],
                remark=_norm_text(row["remark"]),
                line_count=int(row.get("line_count") or 0),
                qty_outbound_total=int(row.get("qty_outbound_total") or 0),
                reversible=reason is None,
                non_reversible_reason=reason,
            )
        )

    return OutboundReversalOptionsOut(items=items)


async def get_outbound_reversal_detail(
    session: AsyncSession,
    *,
    event_id: int,
) -> OutboundReversalDetailOut:
    header = await get_outbound_reversal_detail_header(
        session,
        event_id=int(event_id),
    )
    source_lines = await list_outbound_event_lines_for_reversal(
        session,
        event_id=int(event_id),
    )
    reason = await _non_reversible_reason(session, header)

    lines = [
        OutboundReversalDetailLineOut(
            ref_line=int(src["ref_line"]),
            item_id=int(src["item_id"]),
            item_name_snapshot=_norm_text(src["item_name_snapshot"]),
            item_sku_snapshot=_norm_text(src["item_sku_snapshot"]),
            item_spec_snapshot=_norm_text(src["item_spec_snapshot"]),
            qty_outbound=int(src["qty_outbound"]),
            lot_id=int(src["lot_id"]),
            lot_code_snapshot=_norm_text(src["lot_code_snapshot"]),
            order_line_id=(int(src["order_line_id"]) if src["order_line_id"] is not None else None),
            manual_doc_line_id=(int(src["manual_doc_line_id"]) if src["manual_doc_line_id"] is not None else None),
            remark=_norm_text(src["remark"]),
        )
        for src in source_lines
    ]

    return OutboundReversalDetailOut(
        event_id=int(header["event_id"]),
        event_no=str(header["event_no"]),
        warehouse_id=int(header["warehouse_id"]),
        source_type=str(header["source_type"]),
        source_ref=_norm_text(header["source_ref"]),
        occurred_at=header["occurred_at"],
        committed_at=header["committed_at"],
        status=str(header["status"]),
        remark=_norm_text(header["remark"]),
        line_count=int(header.get("line_count") or len(lines)),
        qty_outbound_total=int(header.get("qty_outbound_total") or 0),
        reversible=reason is None,
        non_reversible_reason=reason,
        lines=lines,
    )


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

    await ensure_warehouse_not_frozen(
        session,
        warehouse_id=int(original["warehouse_id"]),
    )

    occurred_at = payload.occurred_at
    operator_name_snapshot = str(payload.operator_name_snapshot).strip()
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
            lot_code=None,
            production_date=None,
            expiry_date=None,
            trace_id=str(trace_id),
            meta={
                "sub_reason": "OUTBOUND_REVERSAL",
                "event_id": int(event.id),
                "target_event_id": int(original["event_id"]),
                "source_type": str(original["source_type"]),
                "source_ref": _norm_text(original["source_ref"]),
                "operator_name_snapshot": operator_name_snapshot,
                "remark": _norm_text(event.remark),
            },
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
        operator_name_snapshot=operator_name_snapshot,
        remark=_norm_text(event.remark),
        rows=rows,
    )


__all__ = [
    "list_outbound_reversal_options",
    "get_outbound_reversal_detail",
    "reverse_outbound_event",
]
