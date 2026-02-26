# app/services/purchase_order_receive_workbench_queries.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.batch_code_contract import normalize_optional_batch_code
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


async def load_po_confirmed_received_map(session: AsyncSession, *, po_id: int) -> Dict[int, int]:
    """
    聚合口径：只统计 CONFIRMED receipts 的 inbound_receipt_lines.qty_received
    维度：po_line_id -> sum(qty_received)
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.po_line_id,
                        SUM(COALESCE(rl.qty_received, 0)) AS qty
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
    Phase L：confirmed 聚合迁移为 lot_id 维度
    - 聚合维度：po_line_id + lot_id（batch_code 仅展示字段）
    - production_date/expiry_date 作为 canonical 字段，后续统一从 lots 回填
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT
                        rl.po_line_id,
                        rl.lot_id,
                        rl.batch_code,
                        SUM(COALESCE(rl.qty_received, 0)) AS qty
                      FROM inbound_receipt_lines AS rl
                      JOIN inbound_receipts AS r
                        ON r.id = rl.receipt_id
                     WHERE r.source_type = 'PO'
                       AND r.source_id = :po_id
                       AND r.status = 'CONFIRMED'
                       AND rl.po_line_id IS NOT NULL
                       AND rl.lot_id IS NOT NULL
                     GROUP BY rl.po_line_id, rl.lot_id, rl.batch_code
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
        bc_norm = normalize_optional_batch_code(r.get("batch_code"))
        out.setdefault(po_line_id, []).append(
            WorkbenchBatchRowOut(
                lot_id=lot_id,  # Phase L：新增字段（schema 为 Optional[int] 兼容旧前端）
                batch_code=bc_norm,
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
    - draft_map: po_line_id -> sum(qty_received)
    - batch_rows_map: po_line_id -> list[WorkbenchBatchRowOut]（Phase L：按 po_line_id + lot_id 聚合）

    注意：production_date/expiry_date 不从 receipt_line 取，统一交给 canonical 回填。
    """
    draft_map: Dict[int, int] = {}
    batch_rows_map: Dict[int, List[WorkbenchBatchRowOut]] = {}

    if draft is None or not getattr(draft, "lines", None):
        return draft_map, batch_rows_map

    # key: (po_line_id, lot_id) -> payload
    tmp: Dict[Tuple[int, int], Dict[str, object]] = {}

    for rl in draft.lines:
        po_line_id = getattr(rl, "po_line_id", None)
        if po_line_id is None:
            continue

        po_line_id_i = int(po_line_id)
        qty = int(getattr(rl, "qty_received", 0) or 0)
        draft_map[po_line_id_i] = int(draft_map.get(po_line_id_i, 0) + qty)

        lot_id_raw = getattr(rl, "lot_id", None)
        if lot_id_raw is None:
            # DB 侧应为 NOT NULL；这里兜底跳过（同时上层 explain/validate 应当报错）
            continue
        lot_id_i = int(lot_id_raw)

        key = (po_line_id_i, lot_id_i)
        if key not in tmp:
            tmp[key] = {
                "qty": 0,
                # batch_code 仅展示字段：保持 None/null 语义，不制造 NULL_BATCH token
                "batch_code": normalize_optional_batch_code(getattr(rl, "batch_code", None)),
            }
        tmp[key]["qty"] = int(tmp[key]["qty"]) + qty

    for (po_line_id_i, lot_id_i), payload in tmp.items():
        qty = int(payload.get("qty") or 0)
        bc_norm = payload.get("batch_code")
        batch_rows_map.setdefault(po_line_id_i, []).append(
            WorkbenchBatchRowOut(
                lot_id=lot_id_i,  # Phase L：新增字段（schema 为 Optional[int] 兼容旧前端）
                batch_code=bc_norm,  # type: ignore[arg-type]
                production_date=None,
                expiry_date=None,
                qty_received=int(qty),
            )
        )

    return draft_map, batch_rows_map
