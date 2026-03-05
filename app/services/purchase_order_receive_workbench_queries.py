# app/services/purchase_order_receive_workbench_queries.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.lot_code_contract import normalize_optional_lot_code
from app.models.inbound_receipt import InboundReceipt
from app.schemas.purchase_order_receive_workbench import WorkbenchBatchRowOut


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


def build_draft_received_aggregates(
    *, draft: Optional[InboundReceipt]
) -> Tuple[Dict[int, int], Dict[int, List[WorkbenchBatchRowOut]]]:
    """
    Build:
      - draft_map: {po_line_id -> total_qty_base}
      - draft_rows_map: {po_line_id -> [WorkbenchBatchRowOut...]}

    Phase M-5:
    - inbound_receipt_lines 输入展示码字段为 lot_code_input（历史兼容字段名在 ORM 里可能仍叫 batch_code）
    - draft 阶段允许 lot_id 为空（尚未 confirm），因此 WorkbenchBatchRowOut.lot_id 使用 0 作为占位
      （仅用于 workbench 展示聚合，不作为库存事实维度）
    """
    draft_map: Dict[int, int] = {}
    draft_rows_map: Dict[int, List[WorkbenchBatchRowOut]] = {}

    if draft is None or not getattr(draft, "lines", None):
        return draft_map, draft_rows_map

    for ln in draft.lines:
        po_line_id = getattr(ln, "po_line_id", None)
        if po_line_id is None:
            continue

        pid = int(po_line_id)
        qty_base = int(getattr(ln, "qty_base", 0) or 0)
        draft_map[pid] = int(draft_map.get(pid, 0)) + qty_base

        lot_id = getattr(ln, "lot_id", None)
        bc_raw = getattr(ln, "lot_code_input", None)
        if bc_raw is None:
            # 兼容旧属性名（若 ORM 仍暴露 batch_code）
            bc_raw = getattr(ln, "batch_code", None)

        draft_rows_map.setdefault(pid, []).append(
            WorkbenchBatchRowOut(
                lot_id=int(lot_id) if lot_id is not None else 0,
                batch_code=normalize_optional_lot_code(bc_raw),
                production_date=getattr(ln, "production_date", None),
                expiry_date=getattr(ln, "expiry_date", None),
                qty_base=qty_base,
            )
        )

    return draft_map, draft_rows_map


async def load_po_confirmed_received_map(
    session: AsyncSession, *, po_id: int
) -> Dict[int, int]:
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
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.po_line_id,
                        rl.lot_id,
                        rl.lot_code_input,
                        SUM(COALESCE(rl.qty_base, 0)) AS qty
                      FROM inbound_receipt_lines AS rl
                      JOIN inbound_receipts AS r
                        ON r.id = rl.receipt_id
                     WHERE r.source_type = 'PO'
                       AND r.source_id = :po_id
                       AND r.status = 'CONFIRMED'
                       AND rl.po_line_id IS NOT NULL
                       AND rl.lot_id IS NOT NULL
                     GROUP BY rl.po_line_id, rl.lot_id, rl.lot_code_input
                     ORDER BY rl.po_line_id, rl.lot_id
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
        lot_id = int(r["lot_id"])
        bc_norm = normalize_optional_lot_code(r.get("lot_code_input"))
        out.setdefault(po_line_id, []).append(
            WorkbenchBatchRowOut(
                lot_id=lot_id,
                batch_code=bc_norm,
                production_date=None,
                expiry_date=None,
                qty_base=int(r.get("qty") or 0),
            )
        )
    return out
