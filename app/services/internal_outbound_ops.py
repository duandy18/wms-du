# app/services/internal_outbound_ops.py
from __future__ import annotations

from datetime import datetime
from typing import Optional, Set

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lot_code_contract import fetch_item_expiry_policy_map, validate_lot_code_contract
from app.api.problem import raise_problem
from app.models.internal_outbound import InternalOutboundDoc
from app.services.audit_writer import AuditEventWriter
from app.services.internal_outbound_ids import UTC, gen_doc_no, gen_trace_id
from app.services.internal_outbound_query import get_with_lines
from app.services.stock_service import StockService


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
    终态（Batch-as-Lot）：
    - REQUIRED 商品：必须显式批次（SUPPLIER lot_code），禁止自动挑 lot（包括 FEFO）。
    - 找不到 lot 直接硬拦（409）。
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


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


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

    # 预取 policy map（真相源：items.expiry_policy）
    item_ids: Set[int] = {int(ln.item_id) for ln in (doc.lines or []) if ln and int(getattr(ln, "item_id", 0) or 0) > 0}
    pol_map = await fetch_item_expiry_policy_map(session, item_ids)

    missing = [i for i in sorted(item_ids) if i not in pol_map]
    if missing:
        raise ValueError(f"unknown item_id(s): {missing}")

    for line in doc.lines:
        qty = line.confirmed_qty if line.confirmed_qty is not None else line.requested_qty
        qty = int(qty or 0)
        if qty <= 0:
            continue

        requires_batch = _requires_batch_from_expiry_policy(pol_map.get(int(line.item_id)))

        # 终态合同裁决：
        # - REQUIRED：必须批次
        # - NONE：必须不传批次（扣 INTERNAL 槽位）
        norm_bc = validate_lot_code_contract(requires_batch=requires_batch, lot_code=(str(line.batch_code).strip() if line.batch_code else None))

        if requires_batch:
            lot_id = await _resolve_supplier_lot_id_by_lot_code(
                session,
                warehouse_id=int(doc.warehouse_id),
                item_id=int(line.item_id),
                lot_code=str(norm_bc or ""),
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
                batch_code=str(norm_bc),
                meta={"sub_reason": "INT_OUT_EXPL"},
            )
        else:
            # NONE：不允许 batch_code；扣 INTERNAL 槽位（由 StockService.ensure internal lot）
            await stock_svc.adjust(
                session=session,
                item_id=int(line.item_id),
                warehouse_id=int(doc.warehouse_id),
                delta=-int(qty),
                reason="INTERNAL_OUT",
                ref=str(ref),
                ref_line=int(line.line_no),
                occurred_at=now,
                batch_code=None,
                trace_id=trace_id,
                meta={"sub_reason": "INT_OUT_INTERNAL"},
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
