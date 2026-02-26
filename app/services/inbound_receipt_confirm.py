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
from app.models.item import Item
from app.schemas.inbound_receipt import InboundReceiptOut
from app.schemas.inbound_receipt_confirm import (
    InboundReceiptConfirmLedgerRef,
    InboundReceiptConfirmOut,
)
from app.services.domain.lot_service import resolve_or_create_lot
from app.services.inbound_receipt_explain import explain_receipt
from app.services.stock_service import StockService

UTC = timezone.utc

# Phase L：
# - “无批次”应当由 batch_code=None 表达（并由 lot_id 作为身份锚点），而不是让用户输入 NULL_BATCH token。
# - 仍然禁止人为伪码（如 NOEXP/NONE）作为批次。
_PSEUDO_BATCH_TOKENS = {
    "NOEXP",
    "NONE",
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
    if not isinstance(res, dict):
        return None
    if key not in res:
        return None
    return bool(res.get(key))


async def _load_item(session: AsyncSession, *, item_id: int) -> Item:
    stmt = select(Item).where(Item.id == int(item_id)).limit(1)
    obj = (await session.execute(stmt)).scalars().first()
    if obj is None:
        raise_problem(
            status_code=422,
            error_code="ITEM_NOT_FOUND",
            message="收货行商品不存在，无法确认。",
            context={"item_id": int(item_id)},
            details=[{"type": "item", "reason": "item_not_found", "item_id": int(item_id)}],
        )
    return obj


def _safe_int_list(v: object) -> list[int]:
    if v is None:
        return []
    if isinstance(v, list):
        out: list[int] = []
        for x in v:
            try:
                out.append(int(x))
            except Exception:
                continue
        return out
    return []


async def confirm_receipt(
    *,
    session: AsyncSession,
    receipt_id: int,
    user_id: int | None = None,
) -> InboundReceiptConfirmOut:
    _ = user_id

    receipt = await _load_receipt_for_update(session, receipt_id)

    status = str(getattr(receipt, "status", "") or "").upper()

    if status == "CONFIRMED":
        return InboundReceiptConfirmOut(
            receipt=InboundReceiptOut.model_validate(receipt),
            ledger_written=0,
            ledger_refs=[],
        )

    if status != "DRAFT":
        _raise_409_state(receipt_id=receipt_id, status=status)

    exp = await explain_receipt(session=session, receipt=receipt)
    if not exp.confirmable:
        details = [e.model_dump() for e in exp.blocking_errors]
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=details)

    ref = str(getattr(receipt, "ref"))
    occurred_at = getattr(receipt, "occurred_at", None) or datetime.now(UTC)
    warehouse_id = int(getattr(receipt, "warehouse_id"))

    normalized = list(exp.normalized_lines_preview)

    # === Phase 3 修复点 ===
    # 构建 line_no -> lot_id 映射（实体来源）
    line_lot_map: dict[int, Optional[int]] = {}
    for rl in receipt.lines or []:
        ln = int(getattr(rl, "line_no", 0) or 0)
        if ln not in line_lot_map:
            line_lot_map[ln] = rl.lot_id

    # 构建 source_line_index(0-based) -> receipt_line_no(1-based) 映射
    # receipt.lines 已经按 (line_no, id) 排序，index 即对应 explain 的 source_line_indexes
    lines_sorted = list(receipt.lines or [])
    index_to_line_no: dict[int, int] = {}
    for i, rl in enumerate(lines_sorted):
        index_to_line_no[int(i)] = int(getattr(rl, "line_no", 0) or 0)

    def _line_no_from_normalized(n: object) -> int:
        # NormalizedLinePreviewOut 没有 line_no，只有 source_line_indexes
        idxs = _safe_int_list(getattr(n, "source_line_indexes", None))
        if not idxs:
            return 0
        # 取第一个作为代表（同组多行后面会做一致性校验）
        return int(index_to_line_no.get(int(idxs[0]), 0) or 0)

    def _group_line_nos(n: object) -> list[int]:
        idxs = _safe_int_list(getattr(n, "source_line_indexes", None))
        out: list[int] = []
        for i in idxs:
            out.append(int(index_to_line_no.get(int(i), 0) or 0))
        return out

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

        if bc is None and (pd is not None or ed is not None):
            extra_blocking_errors.append(
                {
                    "type": "batch",
                    "reason": "none_mode_dates_must_be_null",
                    "line_key": str(getattr(n, "line_key", "")),
                    "production_date": str(pd) if pd else None,
                    "expiry_date": str(ed) if ed else None,
                }
            )

    if extra_blocking_errors:
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=extra_blocking_errors)

    # ------------------------------------------------------------
    # Phase 4B-0 (主目标前置)：确认收货时强制绑定 lot（INTERNAL identity: receipt_id + line_no）
    # - 让 lot 成为真实入库事实锚点（否则 ledger 永远 lot_coverage=0）
    # - 这里不依赖“上游是否提前创建 lot”，confirm 自己兜底生成
    # ------------------------------------------------------------
    lot_blocking_errors: list[dict] = []
    for n in normalized:
        line_no = _line_no_from_normalized(n)
        item_id = int(getattr(n, "item_id", 0) or 0)

        if line_no <= 0 or item_id <= 0:
            lot_blocking_errors.append(
                {
                    "type": "lot",
                    "reason": "invalid_line_no_or_item_id",
                    "line_key": str(getattr(n, "line_key", "")),
                    "line_no": int(line_no),
                    "item_id": int(item_id),
                }
            )
            continue

        # 同一 normalized group 如果来自多条 receipt_line，必须保证它们的 lot_id 一致（否则库存维度会撕裂）
        group_line_nos = [ln for ln in _group_line_nos(n) if ln > 0]
        if group_line_nos:
            lot_ids: set[int] = set()
            for ln in group_line_nos:
                lid = line_lot_map.get(int(ln))
                if lid is not None:
                    lot_ids.add(int(lid))
            if len(lot_ids) > 1:
                lot_blocking_errors.append(
                    {
                        "type": "lot",
                        "reason": "inconsistent_lot_id_in_group",
                        "line_key": str(getattr(n, "line_key", "")),
                        "line_nos": [int(x) for x in group_line_nos],
                        "lot_ids": [int(x) for x in sorted(lot_ids)],
                        "item_id": int(item_id),
                    }
                )
                continue

        existing_lot_id = line_lot_map.get(line_no)
        if existing_lot_id is not None:
            continue

        # 生成 INTERNAL lot：identity = (warehouse_id, item_id, lot_code_source='INTERNAL', source_receipt_id, source_line_no)
        # dates：沿用 normalized（如果 batch_code=None，则上面已校验 dates 必须为 None）
        bc_norm = normalize_optional_batch_code(getattr(n, "batch_code", None))
        pd = getattr(n, "production_date", None)
        ed = getattr(n, "expiry_date", None)
        if bc_norm is None:
            pd = None
            ed = None

        item_obj = await _load_item(session, item_id=item_id)
        new_lot_id = await resolve_or_create_lot(
            db=session,
            warehouse_id=int(warehouse_id),
            item=item_obj,
            lot_code_source="INTERNAL",
            lot_code=None,
            source_receipt_id=int(receipt.id),
            source_line_no=int(line_no),
            production_date=pd,
            expiry_date=ed,
            expiry_source=None,
            shelf_life_days_applied=None,
        )

        # 回填到 receipt_line（让后续再 confirm / explain / 追溯都能看到实体绑定）
        # receipt.lines 已经 selectinload；按 line_no 找到第一条即可
        for rl in receipt.lines or []:
            ln = int(getattr(rl, "line_no", 0) or 0)
            if ln == line_no:
                rl.lot_id = int(new_lot_id)
                break

        line_lot_map[line_no] = int(new_lot_id)

    if lot_blocking_errors:
        _raise_422_confirm_not_allowed(receipt_id=receipt_id, blocking_errors=lot_blocking_errors)

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

        bc = normalize_optional_batch_code(getattr(n, "batch_code", None))
        pd = getattr(n, "production_date", None)
        ed = getattr(n, "expiry_date", None)

        if bc is None:
            pd = None
            ed = None

        line_no = _line_no_from_normalized(n)
        lot_id = line_lot_map.get(line_no)

        # 最终硬校验：入库必须有 lot_id（主目标驱动）
        if lot_id is None:
            _raise_422_confirm_not_allowed(
                receipt_id=receipt_id,
                blocking_errors=[
                    {
                        "type": "lot",
                        "reason": "lot_id_required_for_receipt_confirm",
                        "line_key": str(getattr(n, "line_key", "")),
                        "line_no": int(line_no),
                        "item_id": int(item_id),
                    }
                ],
            )

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
            batch_code=bc,
            production_date=pd,
            expiry_date=ed,
            trace_id=getattr(receipt, "trace_id", None),
            lot_id=int(lot_id),  # ✅ 现在保证非空
        )

        ledger_refs.append(
            InboundReceiptConfirmLedgerRef(
                source_line_key=str(getattr(n, "line_key", "")),
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

    return InboundReceiptConfirmOut(
        receipt=InboundReceiptOut.model_validate(receipt),
        ledger_written=len(ledger_refs),
        ledger_refs=ledger_refs,
    )
