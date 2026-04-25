# app/wms/inbound/services/inbound_commit_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.services.purchase_order_completion_sync import (
    sync_purchase_completion_for_inbound_event,
)
from app.wms.inbound.contracts.inbound_commit import (
    InboundCommitIn,
    InboundCommitOut,
    InboundCommitResultRow,
)
from app.wms.inbound.models.inbound_event import InboundEventLine, WmsEvent
from app.wms.inbound.repos.barcode_resolve_repo import resolve_inbound_barcode
from app.wms.inbound.repos.inbound_stock_write_repo import apply_inbound_stock
from app.wms.inbound.repos.item_lookup_repo import get_item_policy_by_id
from app.wms.inbound.repos.lot_resolve_repo import resolve_inbound_lot
from app.wms.shared.services.expiry_resolver import normalize_batch_dates_for_item

UTC = timezone.utc
_PSEUDO_LOT_CODE_TOKENS = {"NOEXP", "NONE"}


@dataclass(slots=True)
class ResolvedCommitLine:
    line_no: int
    item_id: int
    item_name_snapshot: str | None
    item_spec_snapshot: str | None
    uom_id: int
    actual_uom_name_snapshot: str | None
    qty_input: int
    ratio_to_base_snapshot: int
    qty_base: int
    barcode_input: str | None
    lot_code_input: str | None
    production_date: date | None
    expiry_date: date | None
    lot_id: int | None
    po_line_id: int | None
    remark: str | None


def _new_trace_id() -> str:
    return f"IN-COMMIT-{uuid4().hex[:20]}"


def _new_event_no() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"IE-{stamp}-{uuid4().hex[:8].upper()}"


def _norm_text(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _norm_lot_code(v: object) -> str | None:
    code = _norm_text(v)
    return code


async def _require_ratio_to_base(
    session: AsyncSession,
    *,
    item_id: int,
    uom_id: int,
) -> int:
    row = await session.execute(
        text(
            """
            SELECT ratio_to_base
            FROM item_uoms
            WHERE id = :uom_id
              AND item_id = :item_id
            LIMIT 1
            """
        ),
        {
            "uom_id": int(uom_id),
            "item_id": int(item_id),
        },
    )
    m = row.mappings().first()
    if m is None:
        raise HTTPException(
            status_code=400,
            detail=f"uom_id 不存在或不属于该商品：item_id={int(item_id)} uom_id={int(uom_id)}",
        )

    try:
        ratio = int(m.get("ratio_to_base") or 0)
    except Exception:
        ratio = 0

    if ratio <= 0:
        raise HTTPException(status_code=400, detail="item_uoms.ratio_to_base 非法（必须 >= 1）")
    return ratio


async def _load_item_display_snapshot(
    session: AsyncSession,
    *,
    item_id: int,
    uom_id: int,
) -> tuple[str | None, str | None, str | None]:
    row = (
        await session.execute(
            text(
                """
                SELECT
                  i.name AS item_name_snapshot,
                  i.spec AS item_spec_snapshot,
                  COALESCE(NULLIF(iu.display_name, ''), iu.uom) AS actual_uom_name_snapshot
                FROM items i
                JOIN item_uoms iu
                  ON iu.id = :uom_id
                 AND iu.item_id = i.id
                WHERE i.id = :item_id
                LIMIT 1
                """
            ),
            {
                "item_id": int(item_id),
                "uom_id": int(uom_id),
            },
        )
    ).mappings().first()

    if row is None:
        raise HTTPException(
            status_code=422,
            detail=f"item_display_snapshot_not_found:{int(item_id)}:{int(uom_id)}",
        )

    return (
        _norm_text(row["item_name_snapshot"]),
        _norm_text(row["item_spec_snapshot"]),
        _norm_text(row["actual_uom_name_snapshot"]),
    )


def _validate_source(payload: InboundCommitIn) -> None:
    if payload.source_type == "PURCHASE_ORDER":
        if not _norm_text(payload.source_ref):
            raise HTTPException(status_code=400, detail="采购入库必须提供 source_ref")
        for idx, line in enumerate(payload.lines, start=1):
            if line.po_line_id is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"采购入库第 {idx} 行必须提供 po_line_id",
                )


async def _resolve_line(
    session: AsyncSession,
    *,
    warehouse_id: int,
    line_no: int,
    source_type: str,
    line: object,
) -> ResolvedCommitLine:
    barcode = _norm_text(getattr(line, "barcode", None))
    item_id_in = getattr(line, "item_id", None)
    uom_id_in = getattr(line, "uom_id", None)
    qty_input = int(getattr(line, "qty_input"))
    lot_code_input = _norm_lot_code(getattr(line, "lot_code_input", None))
    production_date_in = getattr(line, "production_date", None)
    expiry_date_in = getattr(line, "expiry_date", None)
    po_line_id = getattr(line, "po_line_id", None)
    remark = _norm_text(getattr(line, "remark", None))

    if qty_input <= 0:
        raise HTTPException(status_code=400, detail=f"第 {line_no} 行 qty_input 必须 > 0")

    barcode_resolved = None
    if barcode:
        barcode_resolved = await resolve_inbound_barcode(session, barcode=barcode)
        if barcode_resolved is None:
            raise HTTPException(status_code=422, detail=f"barcode_unbound:{barcode}")

    resolved_item_id: int | None = int(item_id_in) if item_id_in is not None else None
    resolved_uom_id: int | None = int(uom_id_in) if uom_id_in is not None else None

    if barcode_resolved is not None:
        if resolved_item_id is None:
            resolved_item_id = int(barcode_resolved.item_id)
        elif resolved_item_id != int(barcode_resolved.item_id):
            raise HTTPException(
                status_code=422,
                detail=f"barcode_item_mismatch:line={line_no}",
            )

        if barcode_resolved.item_uom_id is not None:
            if resolved_uom_id is None:
                resolved_uom_id = int(barcode_resolved.item_uom_id)
            elif resolved_uom_id != int(barcode_resolved.item_uom_id):
                raise HTTPException(
                    status_code=422,
                    detail=f"barcode_uom_mismatch:line={line_no}",
                )

    if resolved_item_id is None:
        raise HTTPException(status_code=422, detail=f"item_unresolved:line={line_no}")
    if resolved_uom_id is None:
        raise HTTPException(status_code=422, detail=f"uom_unresolved:line={line_no}")

    item_policy = await get_item_policy_by_id(session, item_id=int(resolved_item_id))
    if item_policy is None:
        raise HTTPException(status_code=422, detail=f"item_not_found:{resolved_item_id}")

    ratio_to_base_snapshot = await _require_ratio_to_base(
        session,
        item_id=int(resolved_item_id),
        uom_id=int(resolved_uom_id),
    )
    qty_base = int(qty_input) * int(ratio_to_base_snapshot)
    if qty_base <= 0:
        raise HTTPException(status_code=400, detail=f"第 {line_no} 行 qty_base 必须 > 0")

    item_name_snapshot, item_spec_snapshot, actual_uom_name_snapshot = await _load_item_display_snapshot(
        session,
        item_id=int(resolved_item_id),
        uom_id=int(resolved_uom_id),
    )

    if lot_code_input is not None and lot_code_input.upper() in _PSEUDO_LOT_CODE_TOKENS:
        raise HTTPException(status_code=400, detail=f"lot_code 禁止伪码：line={line_no}")

    expiry_policy = str(getattr(item_policy, "expiry_policy", "NONE") or "NONE").upper()
    lot_source_policy = str(
        getattr(item_policy, "lot_source_policy", "INTERNAL_ONLY") or "INTERNAL_ONLY"
    ).upper()

    if lot_source_policy in {"SUPPLIER", "SUPPLIER_ONLY"} and lot_code_input is None:
        raise HTTPException(
            status_code=400,
            detail=f"供应商 lot_code 必填：line={line_no}",
        )

    if expiry_policy == "NONE":
        resolved_production_date = None
        resolved_expiry_date = None
    else:
        resolved_production_date, resolved_expiry_date, _mode = await normalize_batch_dates_for_item(
            session,
            item_id=int(resolved_item_id),
            production_date=production_date_in,
            expiry_date=expiry_date_in,
        )

        if expiry_policy == "REQUIRED":
            if resolved_production_date is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"production_date_unresolved:line={line_no}",
                )
            if resolved_expiry_date is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"expiry_date_unresolved:line={line_no}",
                )

    lot_id = await resolve_inbound_lot(
        session,
        warehouse_id=int(warehouse_id),
        item_policy=item_policy,
        lot_code=lot_code_input,
        production_date=resolved_production_date,
        expiry_date=resolved_expiry_date,
    )

    if source_type != "PURCHASE_ORDER":
        po_line_id = None

    return ResolvedCommitLine(
        line_no=int(line_no),
        item_id=int(resolved_item_id),
        item_name_snapshot=item_name_snapshot,
        item_spec_snapshot=item_spec_snapshot,
        uom_id=int(resolved_uom_id),
        actual_uom_name_snapshot=actual_uom_name_snapshot,
        qty_input=int(qty_input),
        ratio_to_base_snapshot=int(ratio_to_base_snapshot),
        qty_base=int(qty_base),
        barcode_input=barcode,
        lot_code_input=lot_code_input,
        production_date=resolved_production_date,
        expiry_date=resolved_expiry_date,
        lot_id=int(lot_id) if lot_id is not None else None,
        po_line_id=int(po_line_id) if po_line_id is not None else None,
        remark=remark,
    )


async def commit_inbound(
    session: AsyncSession,
    *,
    payload: InboundCommitIn,
    user_id: int | None = None,
) -> InboundCommitOut:
    """
    一层式入库提交主链。

    规则：
    - 不持久化后端 draft
    - 一次提交内完成：解析、校验、换算、lot、事件落库、库存/台账写入
    - 已提交后如需修正，应通过后续 reversal / correction 事件处理，而不是直接改原事件
    """
    _validate_source(payload)

    trace_id = _new_trace_id()
    event_no = _new_event_no()

    resolved_lines: list[ResolvedCommitLine] = []

    for idx, line in enumerate(payload.lines, start=1):
        resolved = await _resolve_line(
            session,
            warehouse_id=int(payload.warehouse_id),
            line_no=int(idx),
            source_type=str(payload.source_type),
            line=line,
        )
        resolved_lines.append(resolved)

    event = WmsEvent(
        event_no=str(event_no),
        event_type="INBOUND",
        warehouse_id=int(payload.warehouse_id),
        source_type=str(payload.source_type),
        source_ref=_norm_text(payload.source_ref),
        occurred_at=payload.occurred_at,
        trace_id=str(trace_id),
        event_kind="COMMIT",
        status="COMMITTED",
        created_by=int(user_id) if user_id is not None else None,
        remark=_norm_text(payload.remark),
    )
    session.add(event)
    await session.flush()

    rows: list[InboundCommitResultRow] = []

    for line in resolved_lines:
        event_line = InboundEventLine(
            event_id=int(event.id),
            line_no=int(line.line_no),
            item_id=int(line.item_id),
            item_name_snapshot=line.item_name_snapshot,
            item_spec_snapshot=line.item_spec_snapshot,
            actual_uom_id=int(line.uom_id),
            actual_uom_name_snapshot=line.actual_uom_name_snapshot,
            barcode_input=line.barcode_input,
            actual_qty_input=int(line.qty_input),
            actual_ratio_to_base_snapshot=int(line.ratio_to_base_snapshot),
            qty_base=int(line.qty_base),
            lot_code_input=line.lot_code_input,
            production_date=line.production_date,
            expiry_date=line.expiry_date,
            lot_id=int(line.lot_id) if line.lot_id is not None else None,
            po_line_id=int(line.po_line_id) if line.po_line_id is not None else None,
            remark=line.remark,
        )
        session.add(event_line)
        await session.flush()

        await apply_inbound_stock(
            session,
            warehouse_id=int(payload.warehouse_id),
            item_id=int(line.item_id),
            lot_id=int(line.lot_id or 0),
            qty=int(line.qty_base),
            ref=str(event.event_no),
            ref_line=int(line.line_no),
            occurred_at=payload.occurred_at,
            lot_code=line.lot_code_input,
            production_date=line.production_date,
            expiry_date=line.expiry_date,
            event_id=int(event.id),
            trace_id=str(trace_id),
            source_type=str(payload.source_type),
            source_biz_type=None,
            source_ref=_norm_text(payload.source_ref),
            remark=_norm_text(payload.remark),
        )

        rows.append(
            InboundCommitResultRow(
                line_no=int(line.line_no),
                item_id=int(line.item_id),
                uom_id=int(line.uom_id),
                qty_input=int(line.qty_input),
                ratio_to_base_snapshot=int(line.ratio_to_base_snapshot),
                qty_base=int(line.qty_base),
                lot_id=int(line.lot_id) if line.lot_id is not None else None,
                lot_code=line.lot_code_input,
                po_line_id=int(line.po_line_id) if line.po_line_id is not None else None,
                remark=line.remark,
            )
        )

    await session.flush()

    if str(payload.source_type) == "PURCHASE_ORDER":
        await sync_purchase_completion_for_inbound_event(
            session,
            event_id=int(event.id),
            occurred_at=payload.occurred_at,
        )

    return InboundCommitOut(
        ok=True,
        event_id=int(event.id),
        event_no=str(event.event_no),
        trace_id=str(trace_id),
        warehouse_id=int(payload.warehouse_id),
        source_type=payload.source_type,
        source_ref=_norm_text(payload.source_ref),
        occurred_at=payload.occurred_at,
        remark=_norm_text(payload.remark),
        rows=rows,
    )


__all__ = [
    "ResolvedCommitLine",
    "commit_inbound",
]
