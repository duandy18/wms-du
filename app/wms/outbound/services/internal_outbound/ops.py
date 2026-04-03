# app/wms/outbound/services/internal_outbound/ops.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problem import raise_problem
from app.models.internal_outbound import InternalOutboundDoc
from app.wms.shared.services.audit_writer import AuditEventWriter
from app.wms.outbound.services.internal_outbound.ids import UTC, gen_doc_no, gen_trace_id
from app.wms.outbound.services.internal_outbound.query import get_with_lines
from app.wms.stock.services.stock_service import StockService


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


async def confirm(
    session: AsyncSession,
    *,
    doc_id: int,
    user_id: Optional[int] = None,
) -> InternalOutboundDoc:

    doc = await get_with_lines(session, doc_id, for_update=True)

    if doc.status != "DRAFT":
        raise_problem(
            status_code=409,
            error_code="internal_outbound_not_draft",
            message="只有 DRAFT 状态的内部出库单可以确认。",
            context={"doc_id": int(doc_id), "status": doc.status},
        )

    # 必须有行（否则确认没有意义）
    lines = getattr(doc, "lines", None) or []
    if not lines:
        raise_problem(
            status_code=422,
            error_code="internal_outbound_empty_lines",
            message="内部出库单没有明细行，禁止确认。",
            context={"doc_id": int(doc_id), "doc_no": str(doc.doc_no), "warehouse_id": int(doc.warehouse_id)},
        )

    now = datetime.now(UTC)

    # ✅ 终态：确认 = 扣库存 + 写台账（lot-world）
    stock_svc = StockService()
    ref_line = 1
    for ln in lines:
        item_id = int(getattr(ln, "item_id"))
        qty = int(getattr(ln, "requested_qty"))
        if qty <= 0:
            continue

        batch_code = getattr(ln, "batch_code", None)

        # 走 StockService.adjust，让它兑现终态合同：
        # - REQUIRED：必须带 batch_code
        # - NONE：必须 batch_code=None，走 INTERNAL 单例 lot
        await stock_svc.adjust(
            session=session,
            item_id=item_id,
            warehouse_id=int(doc.warehouse_id),
            delta=-qty,
            reason="INTERNAL_OUT",
            ref=str(doc.doc_no),
            ref_line=int(ref_line),
            occurred_at=now,
            batch_code=(str(batch_code).strip() if batch_code is not None else None) or None,
            trace_id=str(doc.trace_id) if doc.trace_id is not None else None,
            production_date=None,
            expiry_date=None,
        )
        ref_line += 1

    # 扣库成功后再推进状态（避免“已确认但未扣库”的断裂事实）
    doc.status = "CONFIRMED"
    doc.confirmed_by = user_id
    doc.confirmed_at = now

    await session.flush()

    await AuditEventWriter.write(
        session,
        flow="OUTBOUND",
        event="INTERNAL_OUT_CONFIRMED",
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


async def cancel(
    session: AsyncSession,
    *,
    doc_id: int,
    user_id: Optional[int] = None,
) -> InternalOutboundDoc:

    doc = await get_with_lines(session, doc_id, for_update=True)

    if doc.status != "DRAFT":
        raise_problem(
            status_code=409,
            error_code="internal_outbound_not_draft",
            message="只有 DRAFT 状态的内部出库单可以取消。",
            context={"doc_id": int(doc_id), "status": doc.status},
        )

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
