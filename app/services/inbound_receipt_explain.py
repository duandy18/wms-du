# app/services/inbound_receipt_explain.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.inbound_receipt_explain import (
    InboundReceiptExplainOut,
    InboundReceiptSummaryOut,
    LedgerPreviewOut,
    NormalizedLinePreviewOut,
    ProblemItem,
)


@dataclass(frozen=True)
class _ItemRules:
    expiry_policy: str
    lot_source_policy: str


def _sorted_lines(receipt: object) -> List[object]:
    lines = list(getattr(receipt, "lines", []) or [])
    lines.sort(key=lambda x: (int(getattr(x, "line_no", 0) or 0), int(getattr(x, "id", 0) or 0)))
    return lines


async def explain_receipt(*, session: AsyncSession, receipt: object) -> InboundReceiptExplainOut:
    lines = _sorted_lines(receipt)

    blocking: List[ProblemItem] = []

    for idx, ln in enumerate(lines):
        qty = int(getattr(ln, "qty_base", 0) or 0)
        if qty <= 0:
            blocking.append(
                ProblemItem(scope="line", field="qty_base", message="数量必须大于 0", index=idx)
            )

    normalized: List[NormalizedLinePreviewOut] = []
    ledger_preview: List[LedgerPreviewOut] = []

    for idx, ln in enumerate(lines):
        line_no = int(getattr(ln, "line_no", 0) or 0)
        item_id = int(getattr(ln, "item_id", 0) or 0)
        qty = int(getattr(ln, "qty_base", 0) or 0)

        key = f"LINE:{line_no}"

        normalized.append(
            NormalizedLinePreviewOut(
                line_key=key,
                qty_total=qty,
                lot_id=getattr(ln, "lot_id", None),
                item_id=item_id,
                po_line_id=getattr(ln, "po_line_id", None),
                batch_code=getattr(ln, "batch_code", None),
                production_date=getattr(ln, "production_date", None),
                source_line_indexes=[idx],
            )
        )

        ledger_preview.append(
            LedgerPreviewOut(
                action="INBOUND_RECEIPT_CONFIRM",
                warehouse_id=int(getattr(receipt, "warehouse_id")),
                item_id=item_id,
                qty_delta=qty,
                source_line_key=key,
            )
        )

    summary = InboundReceiptSummaryOut(
        id=int(getattr(receipt, "id")),
        status=str(getattr(receipt, "status")),
        occurred_at=getattr(receipt, "occurred_at", None),
        warehouse_id=int(getattr(receipt, "warehouse_id")),
        source_type=str(getattr(receipt, "source_type", None)),
        source_id=getattr(receipt, "source_id", None),
        ref=str(getattr(receipt, "ref", None)),
        trace_id=str(getattr(receipt, "trace_id", None)) if getattr(receipt, "trace_id", None) else None,
    )

    return InboundReceiptExplainOut(
        receipt_summary=summary,
        confirmable=len(blocking) == 0,
        blocking_errors=blocking,
        normalized_lines_preview=normalized,
        ledger_preview=ledger_preview,
    )
