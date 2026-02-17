# app/api/routers/stock_ledger_routes_query_history.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.batch_code_contract import normalize_optional_batch_code
from app.api.routers.stock_ledger_helpers import build_base_ids_stmt, infer_movement_type
from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.models.purchase_order import PurchaseOrder
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerList, LedgerQuery, LedgerRow
from app.schemas.stock_ledger_explain import (
    ExplainAnchor,
    ExplainLedgerRow,
    ExplainPurchaseOrder,
    ExplainPurchaseOrderLine,
    ExplainReceipt,
    ExplainReceiptLine,
    LedgerExplainOut,
)

UTC = timezone.utc
MAX_HISTORY_DAYS = 3650  # 10 years


def _has_anchor(q: LedgerQuery) -> bool:
    """
    历史查询锚点：
    - trace_id/ref 最强
    - item_id 次强
    - reason_canon/sub_reason 也允许作为锚点（配合时间窗）
    """
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
    """
    历史查询时间窗：
    - 必须提供 time_from（避免无界全表扫）
    - time_to 可选，不填则 now
    - 最大跨度 MAX_HISTORY_DAYS（默认 10 年）
    """
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
        """
        台账解释（终态口径）：

        - ledger → receipt → PO（可选）
        - 不再解释 receive_task（执行层已移除）
        - Receipt 是事实源：用 inbound_receipts(ref, trace_id) 定位
        - Ledger 是动作流水：用 stock_ledger(ref, trace_id) 拉取
        """
        ref = (ref or "").strip()
        if not ref:
            raise HTTPException(status_code=400, detail="ref 不能为空。")

        # 1) 定位 receipt（事实源）
        receipt_stmt = select(InboundReceipt).where(InboundReceipt.ref == ref)
        if trace_id and trace_id.strip():
            receipt_stmt = receipt_stmt.where(InboundReceipt.trace_id == trace_id.strip())
        receipt = (await session.execute(receipt_stmt.order_by(InboundReceipt.id.desc()).limit(1))).scalars().first()
        if receipt is None:
            raise HTTPException(status_code=404, detail="未找到对应的收货事实（Receipt）。")

        # 2) 拉 receipt_lines
        lines_stmt = (
            select(InboundReceiptLine)
            .where(InboundReceiptLine.receipt_id == receipt.id)
            .order_by(InboundReceiptLine.line_no.asc(), InboundReceiptLine.id.asc())
        )
        receipt_lines = (await session.execute(lines_stmt)).scalars().all()

        # 3) 拉 ledger 行（动作流水）
        ledger_stmt = select(StockLedger).where(StockLedger.ref == ref)
        if trace_id and trace_id.strip():
            ledger_stmt = ledger_stmt.where(StockLedger.trace_id == trace_id.strip())
        ledger_stmt = (
            ledger_stmt.order_by(StockLedger.occurred_at.asc(), StockLedger.ref_line.asc(), StockLedger.id.asc())
            .limit(limit)
        )
        ledger_rows = (await session.execute(ledger_stmt)).scalars().all()

        # 4) 向上解释：PO（仅基于 Receipt 的 source_type/source_id）
        po_obj: Optional[PurchaseOrder] = None
        if getattr(receipt, "source_type", None) == "PO" and getattr(receipt, "source_id", None) is not None:
            po_obj = await _load_po_with_lines(session, int(receipt.source_id))

        # 5) 组装响应（终态：不再提供 receive_task）
        out = LedgerExplainOut(
            anchor=ExplainAnchor(ref=ref, trace_id=trace_id.strip() if trace_id else None),
            ledger=[ExplainLedgerRow.model_validate(r) for r in ledger_rows],
            receipt=ExplainReceipt.model_validate(receipt),
            receipt_lines=[ExplainReceiptLine.model_validate(ln) for ln in receipt_lines],
            purchase_order=(
                ExplainPurchaseOrder(
                    id=po_obj.id,
                    supplier=po_obj.supplier,
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
        return out

    @router.post("/query-history", response_model=LedgerList)
    async def query_ledger_history(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerList:
        """
        历史台账查询（用于 >90 天窗口）：

        - 必须提供 time_from；
        - 必须提供锚点（trace_id/ref/item_id/reason_canon/sub_reason 任意一项）；
        - 返回结构与 /stock/ledger/query 一致（LedgerList）。
        """
        # ✅ 主线 B：查询级 batch_code 归一（None/空串/'None' -> None）
        # build_base_ids_stmt -> build_common_filters 已统一用 batch_code_key 过滤，这里做入口层防回潮。
        norm_bc = normalize_optional_batch_code(getattr(payload, "batch_code", None))
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
                    batch_code=r.batch_code,
                    trace_id=r.trace_id,
                    movement_type=infer_movement_type(r.reason),
                )
                for r in rows
            ],
        )
