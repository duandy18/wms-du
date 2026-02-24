# app/services/inbound_receipt_confirm.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.batch_code_contract import normalize_optional_batch_code
from app.api.problem import raise_problem
from app.models.enums import MovementType
from app.models.inbound_receipt import InboundReceipt
from app.models.purchase_order import PurchaseOrder
from app.schemas.inbound_receipt import InboundReceiptOut
from app.schemas.inbound_receipt_confirm import (
    InboundReceiptConfirmLedgerRef,
    InboundReceiptConfirmOut,
)
from app.services.inbound_receipt_explain import explain_receipt
from app.services.purchase_order_receive_workbench import get_receive_workbench
from app.services.stock_service import StockService

UTC = timezone.utc

# Phase 1A 红线：禁止伪批次再流入（无论从哪里来）
_PSEUDO_BATCH_TOKENS = {
    "NOEXP",
    "NONE",
    "NULL_BATCH",
    "__NULL_BATCH__",
}


def _is_pseudo_batch_code(batch_code: Optional[str]) -> bool:
    if batch_code is None:
        return False
    s = str(batch_code).strip()
    if not s:
        return False
    return s.upper() in _PSEUDO_BATCH_TOKENS


async def _load_receipt_for_update(session: AsyncSession, receipt_id: int) -> InboundReceipt:
    stmt = (
        select(InboundReceipt)
        .options(selectinload(InboundReceipt.lines))
        .where(InboundReceipt.id == int(receipt_id))
        .with_for_update()
    )
    obj = (await session.execute(stmt)).scalars().first()
    if obj is None:
        raise ValueError("InboundReceipt not found")
    # 稳定顺序（与 explain 保持一致的排序习惯）
    if obj.lines:
        obj.lines.sort(
            key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "id", 0) or 0))
        )
    return obj


def _raise_422_confirm_not_allowed(*, receipt_id: int, blocking_errors: list[dict]) -> None:
    raise_problem(
        status_code=422,
        error_code="RECEIPT_NOT_CONFIRMABLE",
        message="收货单不满足确认条件，请先修正后再确认。",
        context={"receipt_id": int(receipt_id)},
        details=blocking_errors,
    )


def _raise_409_state(*, receipt_id: int, status: str) -> None:
    raise_problem(
        status_code=409,
        error_code="RECEIPT_STATE_CONFLICT",
        message="收货单状态冲突，无法确认。",
        context={"receipt_id": int(receipt_id), "status": str(status)},
        details=[{"type": "state", "reason": f"status={status}"}],
    )


async def _load_next_ref_line_base(session: AsyncSession, *, ref: str, reason: str) -> int:
    """
    继承旧合同：ref_line 必须在 (reason, ref) 维度递增。
    使用 MAX(ref_line) 做基数，confirm 内按 idx 递增。
    """
    row = await session.execute(
        text(
            """
            SELECT COALESCE(MAX(ref_line), 0)
              FROM stock_ledger
             WHERE ref = :ref
               AND reason = :reason
            """
        ),
        {"ref": str(ref), "reason": str(reason)},
    )
    return int(row.scalar() or 0)


def _opt_bool(res: object, key: str) -> bool | None:
    """
    StockService.adjust 的返回 dict 可能不包含 applied/idempotent。
    缺字段时必须返回 None，避免误导为 False。
    """
    if not isinstance(res, dict):
        return None
    if key not in res:
        return None
    return bool(res.get(key))


async def _maybe_auto_close_po_after_confirm(
    *,
    session: AsyncSession,
    receipt: InboundReceipt,
    now: datetime,
) -> None:
    """
    Phase5+：PO 自动关闭（计划生命周期）
    规则：
    - Receipt(CONFIRMED) 写入后，如果该 receipt 属于 PO（source_type='PO'），
      且 PO 处于 CREATED，
      且 workbench 聚合显示所有行 remaining_qty==0，
      则自动关闭 PO：
        status='CLOSED', close_reason='AUTO_COMPLETED', closed_at=now(若为空)

    注意：
    - 这是“计划层状态变更”，不写库存，只做计划终态固化。
    - 必须在同一事务内完成，且对 PO 加锁，避免并发 confirm 竞争。
    """
    source_type = str(getattr(receipt, "source_type", "") or "").upper()
    if source_type != "PO":
        return

    source_id = getattr(receipt, "source_id", None)
    if source_id is None:
        return
    po_id = int(source_id)

    po_obj = (
        (await session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update()))
        .scalars()
        .first()
    )
    if po_obj is None:
        return

    po_status = str(getattr(po_obj, "status", "") or "").upper()
    if po_status != "CREATED":
        return

    wb = await get_receive_workbench(session, po_id=po_id)
    if not wb.rows:
        return

    is_completed = all(int(getattr(r, "remaining_qty", 0) or 0) == 0 for r in wb.rows)
    if not is_completed:
        return

    po_obj.status = "CLOSED"
    if getattr(po_obj, "closed_at", None) is None:
        po_obj.closed_at = now
    if getattr(po_obj, "close_reason", None) is None:
        po_obj.close_reason = "AUTO_COMPLETED"

    await session.flush()


async def confirm_receipt(
    *,
    session: AsyncSession,
    receipt_id: int,
    user_id: int | None = None,
) -> InboundReceiptConfirmOut:
    """
    Phase5：Receipt confirm（唯一库存写入口）
    - 单事务：锁 receipt → 校验（复用 explain）→ 归一化 → StockService.adjust 写 ledger → status=CONFIRMED
    - 幂等：已 CONFIRMED 直接返回（ledger_written=0）

    Phase 1A（批次两态语义正确化）：
    - NONE（batch_code=NULL）：禁止任何 production_date/expiry_date 灰区值写入台账
    - REQUIRED（batch_code!=NULL）：禁止伪批次词；日期不在 confirm 侧“补全/推断”
    """
    _ = user_id  # 预留：未来写 confirmed_by

    receipt = await _load_receipt_for_update(session, receipt_id)

    status = str(getattr(receipt, "status", "") or "").upper()

    # 幂等：已确认直接返回，不重复写库存
    if status == "CONFIRMED":
        return InboundReceiptConfirmOut(
            receipt=InboundReceiptOut.model_validate(receipt),
            ledger_written=0,
            ledger_refs=[],
        )

    # Phase5：只允许 DRAFT → CONFIRMED
    if status != "DRAFT":
        _raise_409_state(receipt_id=receipt_id, status=status)

    # 复用 explain 校验器 + 归一化（保证口径一致）
    exp = await explain_receipt(session=session, receipt=receipt)
    if not exp.confirmable:
        details = [e.model_dump() for e in exp.blocking_errors]
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=details)

    ref = str(getattr(receipt, "ref"))
    occurred_at = getattr(receipt, "occurred_at", None) or datetime.now(UTC)
    warehouse_id = int(getattr(receipt, "warehouse_id"))

    normalized = list(exp.normalized_lines_preview)

    # Phase 1A：在写库存前再加一道“红线”硬守护，避免上游 normalize 漂移导致灰区事实写入
    extra_blocking_errors: list[dict] = []
    for n in normalized:
        bc = normalize_optional_batch_code(getattr(n, "batch_code", None))
        pd = getattr(n, "production_date", None)
        ed = getattr(n, "expiry_date", None)

        if _is_pseudo_batch_code(bc):
            extra_blocking_errors.append(
                {
                    "type": "batch",
                    "reason": "pseudo_batch_code_forbidden",
                    "line_key": str(getattr(n, "line_key", "")),
                    "batch_code": bc,
                }
            )

        # NONE：batch_code is NULL 时，日期必须同时为 NULL（杜绝 production_date=收货日 灰区写入）
        if bc is None and (pd is not None or ed is not None):
            extra_blocking_errors.append(
                {
                    "type": "batch",
                    "reason": "none_mode_dates_must_be_null",
                    "line_key": str(getattr(n, "line_key", "")),
                    "production_date": str(pd) if pd is not None else None,
                    "expiry_date": str(ed) if ed is not None else None,
                }
            )

    if extra_blocking_errors:
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=extra_blocking_errors)

    stock_svc = StockService()

    base_ref_line = await _load_next_ref_line_base(
        session,
        ref=ref,
        reason=MovementType.INBOUND.value,
    )

    ledger_refs: List[InboundReceiptConfirmLedgerRef] = []

    for idx, n in enumerate(normalized, start=1):
        item_id = int(n.item_id)
        qty_delta = int(n.qty_total)
        ref_line = int(base_ref_line + idx)

        # Phase 1A：统一按两态传递 ledger 维度字段
        bc = normalize_optional_batch_code(getattr(n, "batch_code", None))
        pd = getattr(n, "production_date", None)
        ed = getattr(n, "expiry_date", None)

        if bc is None:
            # NONE：强制三空，防止灰区日期写入
            pd = None
            ed = None

        res = await stock_svc.adjust(
            session=session,
            item_id=item_id,
            warehouse_id=warehouse_id,
            delta=qty_delta,
            reason=MovementType.INBOUND,
            ref=ref,
            ref_line=ref_line,
            occurred_at=occurred_at,
            meta={"source": "inbound-receipt-confirm", "receipt_id": int(receipt_id)},
            # ✅ 语义收敛：禁止 str(None)/空串污染；统一归一为 Optional[str]
            batch_code=bc,
            production_date=pd,
            expiry_date=ed,
            trace_id=getattr(receipt, "trace_id", None),
        )

        ledger_refs.append(
            InboundReceiptConfirmLedgerRef(
                source_line_key=str(n.line_key),
                ref=ref,
                ref_line=ref_line,
                item_id=item_id,
                qty_delta=qty_delta,
                idempotent=_opt_bool(res, "idempotent"),
                applied=_opt_bool(res, "applied"),
            )
        )

    receipt.status = "CONFIRMED"
    await session.flush()

    # ✅ Phase5+：自动关闭 PO（全部按计划完成）
    await _maybe_auto_close_po_after_confirm(session=session, receipt=receipt, now=datetime.now(UTC))

    return InboundReceiptConfirmOut(
        receipt=InboundReceiptOut.model_validate(receipt),
        ledger_written=len(ledger_refs),
        ledger_refs=ledger_refs,
    )
