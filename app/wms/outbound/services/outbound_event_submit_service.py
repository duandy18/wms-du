# app/wms/outbound/services/outbound_event_submit_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.orders.repos.order_outbound_view_repo import (
    load_order_outbound_head,
    load_order_outbound_lines,
)
from app.wms.outbound.contracts.manual_submit import (
    ManualOutboundSubmitIn,
    ManualOutboundSubmitOut,
)
from app.wms.outbound.contracts.order_submit import (
    OrderOutboundSubmitIn,
    OrderOutboundSubmitOut,
)
from app.wms.outbound.repos.manual_doc_repo import (
    complete_manual_doc,
    list_manual_doc_progress,
)
from app.wms.outbound.repos.outbound_event_repo import (
    insert_outbound_event,
    insert_outbound_event_lines,
    insert_outbound_stock_ledger,
    load_stocks_lot_for_update,
    update_stocks_lot_qty,
)
from app.wms.inventory_adjustment.count.services.count_freeze_guard_service import (
    ensure_warehouse_not_frozen,
)

UTC = timezone.utc


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


@dataclass(frozen=True)
class OrderSubmitContext:
    order: Mapping[str, Any]
    order_lines_by_id: Dict[int, Mapping[str, Any]]
    source_ref: str


@dataclass(frozen=True)
class ManualSubmitContext:
    doc: Mapping[str, Any]
    doc_lines_by_id: Dict[int, Mapping[str, Any]]
    source_ref: str
    warehouse_id: int


async def load_order_submit_context(
    session: AsyncSession,
    *,
    order_id: int,
) -> OrderSubmitContext:
    head = await load_order_outbound_head(session, order_id=int(order_id))
    rows = await load_order_outbound_lines(session, order_id=int(order_id))
    if not rows:
        raise ValueError(f"order_lines_not_found: order_id={order_id}")

    source_ref = (
        f"ORD:{str(head['platform']).upper()}:"
        f"{str(head['shop_id'])}:"
        f"{str(head['ext_order_no'])}"
    )

    return OrderSubmitContext(
        order=head,
        order_lines_by_id={int(r["id"]): r for r in rows},
        source_ref=source_ref,
    )


async def load_manual_submit_context(
    session: AsyncSession,
    *,
    doc_id: int,
) -> ManualSubmitContext:
    head = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      id,
                      warehouse_id,
                      doc_no,
                      status
                    FROM manual_outbound_docs
                    WHERE id = :doc_id
                    LIMIT 1
                    """
                ),
                {"doc_id": int(doc_id)},
            )
        )
        .mappings()
        .first()
    )
    if not head:
        raise ValueError(f"manual_doc_not_found: id={doc_id}")
    if str(head["status"]) != "RELEASED":
        raise ValueError(f"manual_doc_not_released: id={doc_id}, status={head['status']}")

    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      id,
                      doc_id,
                      line_no,
                      item_id,
                      requested_qty,
                      item_name_snapshot,
                      item_sku_snapshot,
                      item_spec_snapshot
                    FROM manual_outbound_lines
                    WHERE doc_id = :doc_id
                    ORDER BY line_no ASC, id ASC
                    """
                ),
                {"doc_id": int(doc_id)},
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        raise ValueError(f"manual_doc_lines_not_found: doc_id={doc_id}")

    return ManualSubmitContext(
        doc=head,
        doc_lines_by_id={int(r["id"]): r for r in rows},
        source_ref=str(head["doc_no"]),
        warehouse_id=int(head["warehouse_id"]),
    )


async def load_order_submit_progress(
    session: AsyncSession,
    *,
    order_id: int,
) -> Dict[int, Dict[str, int]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                      ol.id AS order_line_id,
                      ol.req_qty,
                      COALESCE(SUM(oel.qty_outbound), 0) AS submitted_qty
                    FROM order_lines ol
                    LEFT JOIN outbound_event_lines oel
                      ON oel.order_line_id = ol.id
                    WHERE ol.order_id = :order_id
                    GROUP BY ol.id, ol.req_qty
                    ORDER BY ol.id ASC
                    """
                ),
                {"order_id": int(order_id)},
            )
        )
        .mappings()
        .all()
    )
    return {
        int(r["order_line_id"]): {
            "req_qty": int(r["req_qty"]),
            "submitted_qty": int(r["submitted_qty"]),
        }
        for r in rows
    }


async def has_orphan_order_outbound_ledger(
    session: AsyncSession,
    *,
    source_ref: str,
    ref_line: int,
    item_id: int,
    warehouse_id: int,
    lot_id: int,
) -> bool:
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                FROM stock_ledger
                WHERE reason = 'OUTBOUND_SHIP'
                  AND ref = :source_ref
                  AND ref_line = :ref_line
                  AND item_id = :item_id
                  AND warehouse_id = :warehouse_id
                  AND lot_id = :lot_id
                  AND event_id IS NULL
                LIMIT 1
                """
            ),
            {
                "source_ref": str(source_ref),
                "ref_line": int(ref_line),
                "item_id": int(item_id),
                "warehouse_id": int(warehouse_id),
                "lot_id": int(lot_id),
            },
        )
    ).first()
    return row is not None


def normalize_order_submit_lines(
    *,
    lines: List[Dict[str, Any]],
    ctx: OrderSubmitContext,
) -> List[Dict[str, Any]]:
    if not lines:
        raise ValueError("empty_outbound_lines")

    normalized: List[Dict[str, Any]] = []
    ref_line = 1

    for raw in lines:
        order_line_id = int(raw["order_line_id"])
        item_id = int(raw["item_id"])
        qty_outbound = int(raw["qty_outbound"])
        lot_id = int(raw["lot_id"])
        lot_code = _clean_text(raw.get("lot_code"))
        remark = _clean_text(raw.get("remark"))

        src = ctx.order_lines_by_id.get(order_line_id)
        if src is None:
            raise ValueError(f"order_line_not_in_order: order_line_id={order_line_id}")

        src_item_id = int(src["item_id"])
        if item_id != src_item_id:
            raise ValueError(
                "order_line_item_mismatch:"
                f" order_line_id={order_line_id},"
                f" submit_item_id={item_id},"
                f" source_item_id={src_item_id}"
            )

        normalized.append(
            {
                "ref_line": ref_line,
                "order_line_id": order_line_id,
                "manual_doc_line_id": None,
                "item_id": item_id,
                "qty_outbound": qty_outbound,
                "lot_id": lot_id,
                "lot_code": lot_code,
                "item_name_snapshot": _clean_text(src.get("item_name")),
                "item_sku_snapshot": _clean_text(src.get("item_sku")),
                "item_spec_snapshot": _clean_text(src.get("item_spec")),
                "remark": remark,
            }
        )
        ref_line += 1

    return normalized


def normalize_manual_submit_lines(
    *,
    lines: List[Dict[str, Any]],
    ctx: ManualSubmitContext,
) -> List[Dict[str, Any]]:
    if not lines:
        raise ValueError("empty_outbound_lines")

    normalized: List[Dict[str, Any]] = []
    ref_line = 1

    for raw in lines:
        manual_doc_line_id = int(raw["manual_doc_line_id"])
        item_id = int(raw["item_id"])
        qty_outbound = int(raw["qty_outbound"])
        lot_id = int(raw["lot_id"])
        lot_code = _clean_text(raw.get("lot_code"))
        remark = _clean_text(raw.get("remark"))

        src = ctx.doc_lines_by_id.get(manual_doc_line_id)
        if src is None:
            raise ValueError(
                f"manual_doc_line_not_in_doc: manual_doc_line_id={manual_doc_line_id}"
            )

        src_item_id = int(src["item_id"])
        if item_id != src_item_id:
            raise ValueError(
                "manual_doc_line_item_mismatch:"
                f" manual_doc_line_id={manual_doc_line_id},"
                f" submit_item_id={item_id},"
                f" source_item_id={src_item_id}"
            )

        normalized.append(
            {
                "ref_line": ref_line,
                "order_line_id": None,
                "manual_doc_line_id": manual_doc_line_id,
                "item_id": item_id,
                "qty_outbound": qty_outbound,
                "lot_id": lot_id,
                "lot_code": lot_code,
                "item_name_snapshot": _clean_text(src.get("item_name_snapshot")),
                "item_sku_snapshot": _clean_text(src.get("item_sku_snapshot")),
                "item_spec_snapshot": _clean_text(src.get("item_spec_snapshot")),
                "remark": remark,
            }
        )
        ref_line += 1

    return normalized


async def _write_event_and_ledger(
    session: AsyncSession,
    *,
    warehouse_id: int,
    source_type: str,
    source_ref: str,
    operator_id: int | None,
    trace_id: str,
    occurred_at: datetime | None,
    remark: str | None,
    normalized_lines: List[Dict[str, Any]],
):
    ts = occurred_at or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)

    await ensure_warehouse_not_frozen(
        session,
        warehouse_id=int(warehouse_id),
    )

    event = await insert_outbound_event(
        session,
        warehouse_id=int(warehouse_id),
        source_type=str(source_type),
        source_ref=str(source_ref),
        occurred_at=ts,
        trace_id=str(trace_id),
        created_by=int(operator_id) if operator_id is not None else None,
        remark=remark,
    )

    saved_lines = await insert_outbound_event_lines(
        session,
        event_id=int(event["id"]),
        lines=normalized_lines,
    )

    for ln in saved_lines:
        current_qty = await load_stocks_lot_for_update(
            session,
            warehouse_id=int(event["warehouse_id"]),
            item_id=int(ln["item_id"]),
            lot_id=int(ln["lot_id"]),
        )
        if current_qty is None:
            raise ValueError(
                f"stock_slot_not_found: warehouse_id={event['warehouse_id']}, item_id={ln['item_id']}, lot_id={ln['lot_id']}"
            )

        qty_outbound = int(ln["qty_outbound"])
        if current_qty < qty_outbound:
            raise ValueError(
                f"insufficient_stock: warehouse_id={event['warehouse_id']}, item_id={ln['item_id']}, lot_id={ln['lot_id']}, current_qty={current_qty}, need_qty={qty_outbound}"
            )

        after_qty = int(current_qty) - qty_outbound

        await insert_outbound_stock_ledger(
            session,
            item_id=int(ln["item_id"]),
            warehouse_id=int(event["warehouse_id"]),
            lot_id=int(ln["lot_id"]),
            qty_outbound=qty_outbound,
            after_qty=after_qty,
            occurred_at=event["occurred_at"],
            source_ref=str(event["source_ref"]),
            ref_line=int(ln["ref_line"]),
            trace_id=str(event["trace_id"]),
            event_id=int(event["id"]),
        )

        await update_stocks_lot_qty(
            session,
            warehouse_id=int(event["warehouse_id"]),
            item_id=int(ln["item_id"]),
            lot_id=int(ln["lot_id"]),
            qty=after_qty,
        )

    return event, saved_lines


async def submit_order_outbound_event(
    session: AsyncSession,
    *,
    order_id: int,
    warehouse_id: int,
    operator_id: int | None,
    trace_id: str,
    payload: OrderOutboundSubmitIn,
    occurred_at: datetime | None = None,
) -> OrderOutboundSubmitOut:
    ctx = await load_order_submit_context(session, order_id=int(order_id))
    normalized = normalize_order_submit_lines(
        lines=[x.model_dump() for x in payload.lines],
        ctx=ctx,
    )

    progress_by_line = await load_order_submit_progress(session, order_id=int(order_id))
    for ln in normalized:
        order_line_id = int(ln["order_line_id"])
        req_qty = int(progress_by_line.get(order_line_id, {}).get("req_qty", 0))
        submitted_qty = int(progress_by_line.get(order_line_id, {}).get("submitted_qty", 0))
        submit_qty = int(ln["qty_outbound"])

        if req_qty <= 0:
            raise ValueError(f"order_line_not_found_or_invalid: order_line_id={order_line_id}")

        if submitted_qty >= req_qty:
            raise ValueError(
                f"order_line_already_completed: order_line_id={order_line_id}, req_qty={req_qty}, submitted_qty={submitted_qty}"
            )

        if submitted_qty + submit_qty > req_qty:
            raise ValueError(
                f"order_line_over_submit: order_line_id={order_line_id}, req_qty={req_qty}, submitted_qty={submitted_qty}, submit_qty={submit_qty}"
            )

        orphan_conflict = await has_orphan_order_outbound_ledger(
            session,
            source_ref=ctx.source_ref,
            ref_line=int(ln["ref_line"]),
            item_id=int(ln["item_id"]),
            warehouse_id=int(warehouse_id),
            lot_id=int(ln["lot_id"]),
        )
        if orphan_conflict:
            raise ValueError(
                f"legacy_orphan_ledger_conflict: source_ref={ctx.source_ref}, ref_line={ln['ref_line']}, item_id={ln['item_id']}, warehouse_id={warehouse_id}, lot_id={ln['lot_id']}"
            )

    event, saved_lines = await _write_event_and_ledger(
        session,
        warehouse_id=int(warehouse_id),
        source_type="ORDER",
        source_ref=ctx.source_ref,
        operator_id=operator_id,
        trace_id=trace_id,
        occurred_at=occurred_at,
        remark=payload.remark,
        normalized_lines=normalized,
    )

    return OrderOutboundSubmitOut(
        status="OK",
        event_id=int(event["id"]),
        trace_id=str(event["trace_id"]),
        event_type="OUTBOUND",
        source_type="ORDER",
        source_ref=str(event["source_ref"]),
        warehouse_id=int(event["warehouse_id"]),
        occurred_at=event["occurred_at"],
        lines_count=len(saved_lines),
    )


async def submit_manual_outbound_event(
    session: AsyncSession,
    *,
    doc_id: int,
    operator_id: int | None,
    trace_id: str,
    payload: ManualOutboundSubmitIn,
    occurred_at: datetime | None = None,
) -> ManualOutboundSubmitOut:
    ctx = await load_manual_submit_context(session, doc_id=int(doc_id))
    normalized = normalize_manual_submit_lines(
        lines=[x.model_dump() for x in payload.lines],
        ctx=ctx,
    )

    event, saved_lines = await _write_event_and_ledger(
        session,
        warehouse_id=int(ctx.warehouse_id),
        source_type="MANUAL",
        source_ref=ctx.source_ref,
        operator_id=operator_id,
        trace_id=trace_id,
        occurred_at=occurred_at,
        remark=payload.remark,
        normalized_lines=normalized,
    )

    progress_rows = await list_manual_doc_progress(session, doc_id=int(doc_id))
    if progress_rows and all(
        int(row["submitted_qty"]) >= int(row["requested_qty"])
        for row in progress_rows
    ):
        await complete_manual_doc(session, doc_id=int(doc_id))

    return ManualOutboundSubmitOut(
        status="OK",
        event_id=int(event["id"]),
        trace_id=str(event["trace_id"]),
        event_type="OUTBOUND",
        source_type="MANUAL",
        source_ref=str(event["source_ref"]),
        warehouse_id=int(event["warehouse_id"]),
        occurred_at=event["occurred_at"],
        lines_count=len(saved_lines),
    )
