# app/services/purchase_order_receive_workbench.py
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.inbound_receipt import InboundReceipt
from app.models.purchase_order import PurchaseOrder
from app.schemas.purchase_order_receive_workbench import (
    PoSummaryOut,
    PurchaseOrderReceiveWorkbenchOut,
    ReceiptSummaryOut,
    WorkbenchBatchRowOut,
    WorkbenchCapsOut,
    WorkbenchExplainOut,
    WorkbenchRowOut,
)
from app.services.inbound_receipt_explain import explain_receipt
from app.services.purchase_order_queries import get_po_with_lines
from app.services.purchase_order_time import UTC
from app.services.qty_base import ordered_base as _ordered_base_impl


def _ordered_base(line) -> int:
    return int(_ordered_base_impl(line) or 0)


def _to_utc(dt: datetime) -> datetime:
    """
    Workbench 统一输出 UTC（Z）风格：
    - 若 dt 带 tzinfo：转为 UTC
    - 若 dt 为 naive：按 UTC 解释（避免本地时区漂移）
    """
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


async def _load_latest_po_draft_receipt_with_lines(
    session: AsyncSession, *, po_id: int
) -> Optional[InboundReceipt]:
    stmt = (
        select(InboundReceipt)
        .options(selectinload(InboundReceipt.lines))
        .where(InboundReceipt.source_type == "PO")
        .where(InboundReceipt.source_id == int(po_id))
        .where(InboundReceipt.status == "DRAFT")
        .order_by(InboundReceipt.id.desc())
        .limit(1)
    )
    obj = (await session.execute(stmt)).scalars().first()
    if obj and obj.lines:
        obj.lines.sort(
            key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "id", 0) or 0))
        )
    return obj


async def _load_po_confirmed_received_map(session: AsyncSession, *, po_id: int) -> Dict[int, int]:
    """
    聚合口径：只统计 CONFIRMED receipts 的 inbound_receipt_lines.qty_received
    维度：po_line_id -> sum(qty_received)
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.po_line_id,
                        SUM(COALESCE(rl.qty_received, 0)) AS qty
                      FROM inbound_receipt_lines AS rl
                      JOIN inbound_receipts AS r
                        ON r.id = rl.receipt_id
                     WHERE r.source_type = 'PO'
                       AND r.source_id = :po_id
                       AND r.status = 'CONFIRMED'
                       AND rl.po_line_id IS NOT NULL
                     GROUP BY rl.po_line_id
                    """
                ),
                {"po_id": int(po_id)},
            )
        )
        .mappings()
        .all()
    )
    out: Dict[int, int] = {}
    for r in rows:
        out[int(r["po_line_id"])] = int(r.get("qty") or 0)
    return out


async def _load_po_confirmed_batches_map(
    session: AsyncSession, *, po_id: int
) -> Dict[int, List[WorkbenchBatchRowOut]]:
    """
    confirmed 批次聚合：
    维度：po_line_id -> list(batch_code, production_date, expiry_date, qty_received)
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.po_line_id,
                        rl.batch_code,
                        rl.production_date,
                        rl.expiry_date,
                        SUM(COALESCE(rl.qty_received, 0)) AS qty
                      FROM inbound_receipt_lines AS rl
                      JOIN inbound_receipts AS r
                        ON r.id = rl.receipt_id
                     WHERE r.source_type = 'PO'
                       AND r.source_id = :po_id
                       AND r.status = 'CONFIRMED'
                       AND rl.po_line_id IS NOT NULL
                     GROUP BY rl.po_line_id, rl.batch_code, rl.production_date, rl.expiry_date
                     ORDER BY rl.po_line_id, rl.batch_code, rl.production_date NULLS FIRST, rl.expiry_date NULLS FIRST
                    """
                ),
                {"po_id": int(po_id)},
            )
        )
        .mappings()
        .all()
    )

    out: Dict[int, List[WorkbenchBatchRowOut]] = {}
    for r in rows:
        po_line_id = int(r["po_line_id"])
        out.setdefault(po_line_id, []).append(
            WorkbenchBatchRowOut(
                batch_code=str(r.get("batch_code") or ""),
                production_date=r.get("production_date"),
                expiry_date=r.get("expiry_date"),
                qty_received=int(r.get("qty") or 0),
            )
        )
    return out


def _build_po_summary(po: PurchaseOrder) -> PoSummaryOut:
    return PoSummaryOut(
        po_id=int(po.id),
        warehouse_id=int(getattr(po, "warehouse_id")),
        supplier_id=getattr(po, "supplier_id", None),
        supplier_name=getattr(po, "supplier_name", None),
        status=getattr(po, "status", None),
        occurred_at=getattr(po, "occurred_at", None),
    )


def _build_receipt_summary(r: InboundReceipt) -> ReceiptSummaryOut:
    occurred_at = getattr(r, "occurred_at")
    return ReceiptSummaryOut(
        receipt_id=int(r.id),
        ref=str(getattr(r, "ref")),
        status=str(getattr(r, "status")),
        occurred_at=_to_utc(occurred_at),
    )


def _sort_batches(xs: List[WorkbenchBatchRowOut]) -> None:
    xs.sort(
        key=lambda x: (
            str(getattr(x, "batch_code", "")),
            str(getattr(x, "production_date", "") or ""),
            str(getattr(x, "expiry_date", "") or ""),
        )
    )


def _merge_batches(
    *,
    confirmed: List[WorkbenchBatchRowOut],
    draft: List[WorkbenchBatchRowOut],
) -> List[WorkbenchBatchRowOut]:
    """
    合并 confirmed + draft，按 (batch_code, production_date, expiry_date) 聚合 qty_received。
    """
    merged: Dict[Tuple[str, Optional[object], Optional[object]], int] = {}
    for b in confirmed:
        key = (str(b.batch_code), b.production_date, b.expiry_date)
        merged[key] = int(merged.get(key, 0) + int(b.qty_received))
    for b in draft:
        key = (str(b.batch_code), b.production_date, b.expiry_date)
        merged[key] = int(merged.get(key, 0) + int(b.qty_received))

    out = [
        WorkbenchBatchRowOut(
            batch_code=str(k[0]),
            production_date=k[1],  # type: ignore[arg-type]
            expiry_date=k[2],  # type: ignore[arg-type]
            qty_received=int(q),
        )
        for k, q in merged.items()
    ]
    _sort_batches(out)
    return out


async def get_receive_workbench(session: AsyncSession, *, po_id: int) -> PurchaseOrderReceiveWorkbenchOut:
    po = await get_po_with_lines(session, int(po_id), for_update=False)
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")

    po_summary = _build_po_summary(po)

    draft = await _load_latest_po_draft_receipt_with_lines(session, po_id=int(po.id))

    confirmed_map = await _load_po_confirmed_received_map(session, po_id=int(po.id))
    confirmed_batches_map = await _load_po_confirmed_batches_map(session, po_id=int(po.id))

    # draft_map: po_line_id -> sum(qty_received)
    draft_map: Dict[int, int] = {}
    # draft_batches_map: po_line_id -> list[WorkbenchBatchRowOut]
    draft_batches_map: Dict[int, List[WorkbenchBatchRowOut]] = {}

    if draft is not None and draft.lines:
        # 以 (po_line_id, batch_code, production_date, expiry_date) 聚合
        tmp: Dict[Tuple[int, str, Optional[object], Optional[object]], int] = {}
        for rl in draft.lines:
            po_line_id = getattr(rl, "po_line_id", None)
            if po_line_id is None:
                continue
            po_line_id_i = int(po_line_id)
            qty = int(getattr(rl, "qty_received", 0) or 0)
            draft_map[po_line_id_i] = int(draft_map.get(po_line_id_i, 0) + qty)

            key = (
                po_line_id_i,
                str(getattr(rl, "batch_code")),
                getattr(rl, "production_date", None),
                getattr(rl, "expiry_date", None),
            )
            tmp[key] = int(tmp.get(key, 0) + qty)

        for (po_line_id_i, batch_code, pd, ed), qty in tmp.items():
            draft_batches_map.setdefault(po_line_id_i, []).append(
                WorkbenchBatchRowOut(
                    batch_code=str(batch_code),
                    production_date=pd,
                    expiry_date=ed,
                    qty_received=int(qty),
                )
            )

        for xs in draft_batches_map.values():
            _sort_batches(xs)

    rows: List[WorkbenchRowOut] = []
    if not getattr(po, "lines", None):
        caps = WorkbenchCapsOut(
            can_confirm=False,
            can_start_draft=True,
            receipt_id=int(draft.id) if draft is not None else None,
        )
        return PurchaseOrderReceiveWorkbenchOut(
            po_summary=po_summary,
            receipt=_build_receipt_summary(draft) if draft is not None else None,
            rows=[],
            explain=None,
            caps=caps,
        )

    for line in po.lines:
        po_line_id = int(getattr(line, "id"))
        ordered = _ordered_base(line)
        confirmed_received = int(confirmed_map.get(po_line_id, 0))
        draft_received = int(draft_map.get(po_line_id, 0))
        remaining = max(int(ordered) - int(confirmed_received) - int(draft_received), 0)

        draft_batches = draft_batches_map.get(po_line_id, [])
        confirmed_batches = confirmed_batches_map.get(po_line_id, [])
        all_batches = _merge_batches(confirmed=confirmed_batches, draft=draft_batches)

        rows.append(
            WorkbenchRowOut(
                po_line_id=po_line_id,
                line_no=int(getattr(line, "line_no", 0) or 0),
                item_id=int(getattr(line, "item_id")),
                item_name=getattr(line, "item_name", None),
                item_sku=getattr(line, "item_sku", None),
                ordered_qty=int(ordered),
                confirmed_received_qty=int(confirmed_received),
                draft_received_qty=int(draft_received),
                remaining_qty=int(remaining),
                batches=draft_batches,
                confirmed_batches=confirmed_batches,
                all_batches=all_batches,
            )
        )

    rows.sort(key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "po_line_id", 0) or 0)))

    explain_out: Optional[WorkbenchExplainOut] = None
    can_confirm = False
    receipt_summary: Optional[ReceiptSummaryOut] = None

    if draft is not None:
        receipt_summary = _build_receipt_summary(draft)
        exp = await explain_receipt(session=session, receipt=draft)
        can_confirm = bool(exp.confirmable)
        explain_out = WorkbenchExplainOut(
            confirmable=bool(exp.confirmable),
            blocking_errors=[e.model_dump() for e in exp.blocking_errors],
            normalized_lines_preview=[x.model_dump() for x in exp.normalized_lines_preview],
        )

    caps = WorkbenchCapsOut(
        can_confirm=bool(can_confirm),
        can_start_draft=True,
        receipt_id=int(draft.id) if draft is not None else None,
    )

    return PurchaseOrderReceiveWorkbenchOut(
        po_summary=po_summary,
        receipt=receipt_summary,
        rows=rows,
        explain=explain_out,
        caps=caps,
    )
