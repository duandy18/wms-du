# app/wms/inventory/routers/stock_ledger_routes_query_history.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.lot_code_contract import normalize_optional_lot_code
from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.lot import Lot
from app.models.purchase_order import PurchaseOrder
from app.models.stock_ledger import StockLedger
from app.wms.ledger.contracts.stock_ledger import LedgerList, LedgerQuery, LedgerRow
from app.wms.ledger.contracts.stock_ledger_explain import (
    ExplainAnchor,
    ExplainLedgerRow,
    ExplainPurchaseOrder,
    ExplainPurchaseOrderLine,
    ExplainReceipt,
    ExplainReceiptLine,
    LedgerExplainOut,
)
from app.wms.ledger.routers.stock_ledger_helpers import build_base_ids_stmt, infer_movement_type

UTC = timezone.utc
MAX_HISTORY_DAYS = 3650


def _has_anchor(q: LedgerQuery) -> bool:
    if q.trace_id and str(q.trace_id).strip():
        return True
    if q.ref and str(q.ref).strip():
        return True
    if q.item_id is not None:
        return True

    rc = getattr(q, "reason_canon", None)
    if rc is not None and str(rc).strip():
        return True

    sr = getattr(q, "sub_reason", None)
    if sr is not None and str(sr).strip():
        return True

    return False


def _normalize_history_time_range(q: LedgerQuery) -> tuple[datetime, datetime]:
    if q.time_from is None:
        raise HTTPException(status_code=400, detail="历史查询必须指定 time_from。")

    t1 = q.time_from
    t2 = q.time_to or datetime.now(UTC)

    if t1.tzinfo is None:
        t1 = t1.replace(tzinfo=UTC)
    if t2.tzinfo is None:
        t2 = t2.replace(tzinfo=UTC)

    if t2 < t1:
        raise HTTPException(status_code=400, detail="time_to 不能早于 time_from。")

    if (t2 - t1) > timedelta(days=MAX_HISTORY_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"时间范围过大，请缩小到 {MAX_HISTORY_DAYS} 天以内。",
        )

    return t1, t2


async def _load_po_with_lines(session: AsyncSession, po_id: int) -> Optional[PurchaseOrder]:
    res = await session.execute(
        select(PurchaseOrder).options(selectinload(PurchaseOrder.lines)).where(PurchaseOrder.id == po_id)
    )
    po = res.scalars().first()
    if po and po.lines:
        po.lines.sort(key=lambda ln: (ln.line_no, ln.id))
    return po


def register(router: APIRouter) -> None:
    @router.get("/explain", response_model=LedgerExplainOut)
    async def explain_ledger_ref(
        ref: str = Query(..., description="业务 ref（例如 RT-230 / RMA-xxx）"),
        trace_id: Optional[str] = Query(None, description="可选：trace_id（强烈建议传，避免歧义）"),
        limit: int = Query(300, ge=1, le=2000, description="最多返回多少条 ledger 行"),
        session: AsyncSession = Depends(get_session),
    ) -> LedgerExplainOut:
        ref = (ref or "").strip()
        if not ref:
            raise HTTPException(status_code=400, detail="ref 不能为空。")

        receipt_stmt = select(InboundReceipt).where(InboundReceipt.ref == ref)
        if trace_id and trace_id.strip():
            receipt_stmt = receipt_stmt.where(InboundReceipt.trace_id == trace_id.strip())
        receipt = (await session.execute(receipt_stmt.order_by(InboundReceipt.id.desc()).limit(1))).scalars().first()
        if receipt is None:
            raise HTTPException(status_code=404, detail="未找到对应的收货事实（Receipt）。")

        lines_stmt = (
            select(InboundReceiptLine)
            .where(InboundReceiptLine.receipt_id == receipt.id)
            .order_by(InboundReceiptLine.line_no.asc(), InboundReceiptLine.id.asc())
        )
        receipt_lines = (await session.execute(lines_stmt)).scalars().all()

        ledger_stmt = select(StockLedger).where(StockLedger.ref == ref)
        if trace_id and trace_id.strip():
            ledger_stmt = ledger_stmt.where(StockLedger.trace_id == trace_id.strip())
        ledger_stmt = (
            ledger_stmt.order_by(StockLedger.occurred_at.asc(), StockLedger.ref_line.asc(), StockLedger.id.asc())
            .limit(limit)
        )
        ledger_rows = (await session.execute(ledger_stmt)).scalars().all()

        po_obj: Optional[PurchaseOrder] = None
        if getattr(receipt, "source_type", None) == "PO" and getattr(receipt, "source_id", None) is not None:
            po_obj = await _load_po_with_lines(session, int(receipt.source_id))

        return LedgerExplainOut(
            anchor=ExplainAnchor(ref=ref, trace_id=trace_id.strip() if trace_id else None),
            ledger=[ExplainLedgerRow.model_validate(r) for r in ledger_rows],
            receipt=ExplainReceipt.model_validate(receipt),
            receipt_lines=[ExplainReceiptLine.model_validate(ln) for ln in receipt_lines],
            purchase_order=(
                ExplainPurchaseOrder(
                    id=po_obj.id,
                    supplier_id=po_obj.supplier_id,
                    supplier_name=po_obj.supplier_name,
                    warehouse_id=po_obj.warehouse_id,
                    purchaser=po_obj.purchaser,
                    purchase_time=po_obj.purchase_time,
                    remark=po_obj.remark,
                    status=po_obj.status,
                    created_at=po_obj.created_at,
                    updated_at=po_obj.updated_at,
                    last_received_at=po_obj.last_received_at,
                    closed_at=po_obj.closed_at,
                    lines=[ExplainPurchaseOrderLine.model_validate(ln) for ln in (po_obj.lines or [])],
                )
                if po_obj is not None
                else None
            ),
        )

    @router.post("/query-history", response_model=LedgerList)
    async def query_ledger_history(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerList:
        norm_bc = normalize_optional_lot_code(getattr(payload, "batch_code", None))
        if getattr(payload, "batch_code", None) != norm_bc:
            payload = payload.model_copy(update={"batch_code": norm_bc})

        if not _has_anchor(payload):
            raise HTTPException(
                status_code=400,
                detail="历史查询必须至少指定：trace_id / ref / item_id / reason_canon / sub_reason（任意一项）。",
            )

        time_from, time_to = _normalize_history_time_range(payload)

        ids_stmt = build_base_ids_stmt(payload, time_from, time_to)
        ids_subq = ids_stmt.subquery()

        total = (await session.execute(select(func.count()).select_from(ids_subq))).scalar_one()

        list_stmt = (
            select(StockLedger)
            .where(StockLedger.id.in_(select(ids_subq.c.id)))
            .order_by(StockLedger.occurred_at.desc(), StockLedger.id.desc())
            .limit(payload.limit)
            .offset(payload.offset)
        )
        rows = (await session.execute(list_stmt)).scalars().all()

        lot_ids = sorted({int(getattr(r, "lot_id")) for r in rows if getattr(r, "lot_id", None) is not None})
        lot_code_map: dict[int, str | None] = {}
        if lot_ids:
            res = await session.execute(select(Lot.id, Lot.lot_code).where(Lot.id.in_(lot_ids)))
            for lot_id, lot_code in res.all():
                lot_code_map[int(lot_id)] = lot_code

        return LedgerList(
            total=total,
            items=[
                LedgerRow(
                    id=r.id,
                    delta=r.delta,
                    reason=r.reason,
                    reason_canon=getattr(r, "reason_canon", None),
                    sub_reason=getattr(r, "sub_reason", None),
                    ref=r.ref,
                    ref_line=r.ref_line,
                    occurred_at=r.occurred_at,
                    created_at=r.created_at,
                    after_qty=r.after_qty,
                    item_id=r.item_id,
                    item_name=getattr(r, "item_name", None),
                    warehouse_id=r.warehouse_id,
                    batch_code=lot_code_map.get(int(getattr(r, "lot_id"))) if getattr(r, "lot_id", None) is not None else None,
                    lot_code=lot_code_map.get(int(getattr(r, "lot_id"))) if getattr(r, "lot_id", None) is not None else None,
                    lot_id=getattr(r, "lot_id", None),
                    trace_id=r.trace_id,
                    movement_type=infer_movement_type(r.reason),
                )
                for r in rows
            ],
        )
