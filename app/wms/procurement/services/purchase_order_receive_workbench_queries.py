# app/wms/procurement/services/purchase_order_receive_workbench_queries.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.wms.shared.services.lot_code_contract import normalize_optional_lot_code
from app.models.inbound_receipt import InboundReceipt
from app.wms.procurement.contracts.purchase_order_receive_workbench import WorkbenchBatchRowOut


async def load_latest_po_draft_receipt_with_lines(
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


async def load_po_confirmed_received_map(session: AsyncSession, *, po_id: int) -> Dict[int, int]:
    """
    聚合口径：只统计 CONFIRMED receipts 的 inbound_receipt_lines.qty_base
    维度：po_line_id -> sum(qty_base)
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.po_line_id,
                        SUM(COALESCE(rl.qty_base, 0)) AS qty
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


async def load_po_confirmed_batch_rows_map(
    session: AsyncSession, *, po_id: int
) -> Dict[int, List[WorkbenchBatchRowOut]]:
    """
    confirmed 批次聚合（语义收敛版）：
    - 聚合维度：po_line_id + lot_code（不再把 receipt_line 的 production/expiry 纳入 key）
    - production_date/expiry_date 作为 canonical 字段，后续统一从 batches 回填
    - 数量口径：qty_base
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.po_line_id,
                        rl.lot_code_input,
                        SUM(COALESCE(rl.qty_base, 0)) AS qty
                      FROM inbound_receipt_lines AS rl
                      JOIN inbound_receipts AS r
                        ON r.id = rl.receipt_id
                     WHERE r.source_type = 'PO'
                       AND r.source_id = :po_id
                       AND r.status = 'CONFIRMED'
                       AND rl.po_line_id IS NOT NULL
                     GROUP BY rl.po_line_id, rl.lot_code_input
                     ORDER BY rl.po_line_id, rl.lot_code_input
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
        lot_code_norm = normalize_optional_lot_code(r.get("lot_code_input"))
        out.setdefault(po_line_id, []).append(
            WorkbenchBatchRowOut(
                lot_code=lot_code_norm,
                production_date=None,
                expiry_date=None,
                qty_received=int(r.get("qty") or 0),
            )
        )
    return out


def build_draft_received_aggregates(
    *,
    draft: Optional[InboundReceipt],
) -> Tuple[Dict[int, int], Dict[int, List[WorkbenchBatchRowOut]]]:
    """
    从 draft receipt.lines 聚合：
    - draft_map: po_line_id -> sum(qty_base)
    - draft_batches_map: po_line_id -> list[WorkbenchBatchRowOut]（按 po_line_id + lot_code_norm 聚合）
    注意：production_date/expiry_date 不从 receipt_line 取，统一交给 canonical 回填。
    """
    draft_map: Dict[int, int] = {}
    draft_batches_map: Dict[int, List[WorkbenchBatchRowOut]] = {}

    if draft is None or not getattr(draft, "lines", None):
        return draft_map, draft_batches_map

    tmp: Dict[Tuple[int, Optional[str]], int] = {}
    for rl in draft.lines:
        po_line_id = getattr(rl, "po_line_id", None)
        if po_line_id is None:
            continue

        po_line_id_i = int(po_line_id)
        qty = int(getattr(rl, "qty_base", 0) or 0)
        draft_map[po_line_id_i] = int(draft_map.get(po_line_id_i, 0) + qty)

        lot_code_norm = normalize_optional_lot_code(getattr(rl, "lot_code_input", None))
        key = (po_line_id_i, lot_code_norm)
        tmp[key] = int(tmp.get(key, 0) + qty)

    for (po_line_id_i, lot_code_norm), qty in tmp.items():
        draft_batches_map.setdefault(po_line_id_i, []).append(
            WorkbenchBatchRowOut(
                lot_code=lot_code_norm,
                production_date=None,
                expiry_date=None,
                qty_received=int(qty),
            )
        )

    return draft_map, draft_batches_map
