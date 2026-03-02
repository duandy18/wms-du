# app/services/internal_outbound_ops.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.problem import raise_problem
from app.models.internal_outbound import InternalOutboundDoc
from app.services.audit_writer import AuditEventWriter
from app.services.stock_service import StockService

from app.services.internal_outbound_ids import UTC, gen_doc_no, gen_trace_id
from app.services.internal_outbound_query import get_with_lines


async def create_doc(
    session: AsyncSession,
    *,
    warehouse_id: int,
    doc_type: str,
    recipient_name: str,
    recipient_type: Optional[str] = None,
    recipient_note: Optional[str] = None,
    note: Optional[str] = None,
    created_by: Optional[int] = None,
    trace_id: Optional[str] = None,
) -> InternalOutboundDoc:
    if not recipient_name or not recipient_name.strip():
        raise ValueError("内部出库单必须填写领取人姓名（recipient_name）")

    doc_no = gen_doc_no(warehouse_id)
    ti = trace_id or gen_trace_id(warehouse_id, doc_no)
    now = datetime.now(UTC)

    doc = InternalOutboundDoc(
        warehouse_id=warehouse_id,
        doc_no=doc_no,
        doc_type=doc_type,
        status="DRAFT",
        recipient_name=recipient_name.strip(),
        recipient_type=recipient_type,
        recipient_note=recipient_note,
        note=note,
        created_by=created_by,
        created_at=now,
        trace_id=ti,
    )
    session.add(doc)
    await session.flush()

    await AuditEventWriter.write(
        session,
        flow="OUTBOUND",
        event="INTERNAL_OUT_CREATED",
        ref=doc_no,
        trace_id=ti,
        meta={
            "doc_id": doc.id,
            "doc_no": doc_no,
            "warehouse_id": warehouse_id,
            "doc_type": doc.doc_type,
            "recipient_name": doc.recipient_name,
        },
        auto_commit=False,
    )

    return await get_with_lines(session, doc.id)


async def _resolve_supplier_lot_id_by_lot_code(
    session: AsyncSession,
    *,
    warehouse_id: int,
    item_id: int,
    lot_code: str,
) -> int:
    """
    终态（lot-only）：
    - 显式 batch_code 已演进为 SUPPLIER lot_code（lot-world）
    - 执行域禁止 fallback 到 batch-world
    - 找不到 lot 直接硬拦（409）
    """
    code = (lot_code or "").strip()
    if not code:
        raise ValueError("lot_code 不能为空")

    row = (
        await session.execute(
            text(
                """
                SELECT id
                  FROM lots
                 WHERE warehouse_id = :w
                   AND item_id      = :i
                   AND lot_code_source = 'SUPPLIER'
                   AND lot_code = :c
                 LIMIT 1
                """
            ),
            {"w": int(warehouse_id), "i": int(item_id), "c": str(code)},
        )
    ).first()

    if not row:
        raise_problem(
            status_code=409,
            error_code="lot_not_found",
            message="批次不存在（lot-world），禁止执行出库。",
            context={"warehouse_id": int(warehouse_id), "item_id": int(item_id), "lot_code": str(code)},
            details=[],
            next_actions=[{"action": "create_lot", "label": "补录批次/入库以生成 lot"}],
        )
        return 0

    return int(row[0])


async def fefo_deduct_internal(
    session: AsyncSession,
    *,
    stock_svc: StockService,
    warehouse_id: int,
    item_id: int,
    total_qty: int,
    ref: str,
    base_ref_line: int,
    trace_id: Optional[str],
) -> None:
    """
    internal_outbound FEFO 扣减（lot-only）：
    - 选槽：stocks_lot + lots（expiry_date ASC NULLS LAST, lot_id ASC）
    - 扣减：StockService.adjust_lot（写 stocks_lot + ledger(lot_id)）
    """
    remain = int(total_qty)
    idx = 0
    now = datetime.now(UTC)

    while remain > 0:
        row = (
            await session.execute(
                text(
                    """
                    SELECT s.lot_id, s.qty
                      FROM stocks_lot s
                      LEFT JOIN lots lo ON lo.id = s.lot_id
                     WHERE s.item_id = :i
                       AND s.warehouse_id = :w
                       AND s.qty > 0
                     ORDER BY lo.expiry_date ASC NULLS LAST, s.lot_id ASC
                     LIMIT 1
                    """
                ),
                {"i": int(item_id), "w": int(warehouse_id)},
            )
        ).first()

        if not row:
            raise ValueError(f"内部出库 FEFO 扣减失败：库存不足 item_id={item_id}, remain={remain}")

        lot_id = int(row[0])
        on_hand = int(row[1] or 0)
        take = min(remain, on_hand)
        idx += 1

        await stock_svc.adjust_lot(
            session=session,
            item_id=int(item_id),
            warehouse_id=int(warehouse_id),
            lot_id=int(lot_id),
            delta=-int(take),
            reason="INTERNAL_OUT",
            ref=str(ref),
            ref_line=int(base_ref_line) * 100 + int(idx),
            occurred_at=now,
            trace_id=trace_id,
            batch_code=None,
            meta={"sub_reason": "INT_OUT_FEFO"},
        )

        remain -= take


async def confirm(
    session: AsyncSession,
    *,
    stock_svc: StockService,
    doc_id: int,
    user_id: Optional[int] = None,
    occurred_at: Optional[datetime] = None,
) -> InternalOutboundDoc:
    doc = await get_with_lines(session, doc_id, for_update=True)

    if doc.status != "DRAFT":
        raise ValueError(f"内部出库单 {doc.id} 状态为 {doc.status}，不能重复确认")

    if not doc.recipient_name or not doc.recipient_name.strip():
        raise ValueError(f"内部出库单 {doc.id} 未填写领取人姓名（recipient_name），禁止确认出库")

    if not doc.lines:
        raise ValueError(f"内部出库单 {doc.id} 没有任何行，无法确认出库")

    now = occurred_at or datetime.now(UTC)
    ref = doc.doc_no
    trace_id = doc.trace_id or gen_trace_id(doc.warehouse_id, doc.doc_no)

    for line in doc.lines:
        qty = line.confirmed_qty if line.confirmed_qty is not None else line.requested_qty
        qty = int(qty or 0)
        if qty <= 0:
            continue

        if line.batch_code:
            bc = str(line.batch_code).strip()
            lot_id = await _resolve_supplier_lot_id_by_lot_code(
                session,
                warehouse_id=int(doc.warehouse_id),
                item_id=int(line.item_id),
                lot_code=bc,
            )

            await stock_svc.adjust_lot(
                session=session,
                item_id=int(line.item_id),
                warehouse_id=int(doc.warehouse_id),
                lot_id=int(lot_id),
                delta=-int(qty),
                reason="INTERNAL_OUT",
                ref=str(ref),
                ref_line=int(line.line_no),
                occurred_at=now,
                trace_id=trace_id,
                batch_code=bc,
                meta={"sub_reason": "INT_OUT_EXPL"},
            )
        else:
            await fefo_deduct_internal(
                session=session,
                stock_svc=stock_svc,
                warehouse_id=int(doc.warehouse_id),
                item_id=int(line.item_id),
                total_qty=int(qty),
                ref=str(ref),
                base_ref_line=int(line.line_no),
                trace_id=trace_id,
            )

    doc.status = "CONFIRMED"
    doc.confirmed_by = user_id
    doc.confirmed_at = now
    doc.trace_id = trace_id

    await session.flush()

    await AuditEventWriter.write(
        session,
        flow="OUTBOUND",
        event="INTERNAL_OUT_CONFIRMED",
        ref=ref,
        trace_id=trace_id,
        meta={
            "doc_id": doc.id,
            "doc_no": doc.doc_no,
            "warehouse_id": doc.warehouse_id,
            "doc_type": doc.doc_type,
            "recipient_name": doc.recipient_name,
            "lines": [
                {
                    "line_no": ln.line_no,
                    "item_id": ln.item_id,
                    "batch_code": ln.batch_code,
                    "requested_qty": ln.requested_qty,
                    "confirmed_qty": ln.confirmed_qty,
                }
                for ln in (doc.lines or [])
            ],
        },
        auto_commit=False,
    )

    return await get_with_lines(session, doc.id)


async def cancel(
    session: AsyncSession,
    *,
    doc_id: int,
    user_id: Optional[int] = None,
) -> InternalOutboundDoc:
    doc = await get_with_lines(session, doc_id, for_update=True)

    if doc.status != "DRAFT":
        raise ValueError(f"内部出库单 {doc.id} 状态为 {doc.status}，不能取消")

    doc.status = "CANCELED"
    doc.canceled_by = user_id
    doc.canceled_at = datetime.now(UTC)

    await session.flush()

    await AuditEventWriter.write(
        session,
        flow="OUTBOUND",
        event="INTERNAL_OUT_CANCELED",
        ref=doc.doc_no,
        trace_id=doc.trace_id,
        meta={
            "doc_id": doc.id,
            "doc_no": doc.doc_no,
            "warehouse_id": doc.warehouse_id,
            "doc_type": doc.doc_type,
            "recipient_name": doc.recipient_name,
        },
        auto_commit=False,
    )

    return await get_with_lines(session, doc.id)
