# app/services/purchase_order_receipts.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy import bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.schemas.purchase_order_receipts import PurchaseOrderReceiptEventOut


async def _load_po_exists(session: AsyncSession, po_id: int) -> Optional[PurchaseOrder]:
    res = await session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    return res.scalar_one_or_none()


async def _load_line_no_map(session: AsyncSession, po_id: int) -> Dict[int, int]:
    """
    item_id -> line_no（兜底映射）
    - 若同一 item_id 在 PO 中出现多行（不推荐，但可能），取最小 line_no 保持稳定。
    - 正常情况下通过 inbound_receipt_lines.po_line_id 精确映射 line_no。
    """
    res = await session.execute(
        select(PurchaseOrderLine.item_id, PurchaseOrderLine.line_no).where(PurchaseOrderLine.po_id == po_id)
    )
    rows: List[Tuple[int, int]] = [(int(r[0]), int(r[1])) for r in res.all()]
    m: Dict[int, int] = {}
    for item_id, line_no in rows:
        if item_id not in m:
            m[item_id] = line_no
        else:
            m[item_id] = min(m[item_id], line_no)
    return m


async def _load_confirmed_receipt_refs(session: AsyncSession, po_id: int) -> List[str]:
    """
    Phase5+：采购收货事实事件的台账 ref = receipt.ref
    这里只取 CONFIRMED receipts 的 ref（draft 不产生 ledger）。
    """
    res = await session.execute(
        text(
            """
            SELECT ref
              FROM inbound_receipts
             WHERE source_type = 'PO'
               AND source_id = :po_id
               AND status = 'CONFIRMED'
             ORDER BY occurred_at ASC, id ASC
            """
        ),
        {"po_id": int(po_id)},
    )
    rows = res.mappings().all()
    return [str(r["ref"]) for r in rows if r.get("ref")]


async def list_po_receipt_events(session: AsyncSession, po_id: int) -> List[PurchaseOrderReceiptEventOut]:
    """
    采购单历史收货事件（事实口径）：

    Phase5+ 收敛：
    - 台账来自 stock_ledger：reason='RECEIPT'
    - ref 不再是 'PO-{po_id}'，而是 receipt.ref（每次 confirm 固化一张 receipt）

    ⚠️ 重要：避免 join 放大导致同一 ledger 行重复（ref_line 重复）。
    做法：先把 inbound_receipt_lines 按 (receipt_id,item_id,batch_code,production_date) 聚合成唯一映射。
    """
    po = await _load_po_exists(session, po_id)
    if po is None:
        raise ValueError("PurchaseOrder not found")

    refs = await _load_confirmed_receipt_refs(session, po_id)
    if not refs:
        return []

    reason = "RECEIPT"
    fallback_line_no_map = await _load_line_no_map(session, po_id)

    # rl_map：把 receipt_lines 先压成唯一映射，避免一条 ledger 行被多条 receipt_line 匹配导致重复输出
    stmt = (
        text(
            """
            WITH rl_map AS (
              SELECT
                rl.receipt_id,
                rl.item_id,
                rl.batch_code,
                rl.production_date,
                MIN(rl.po_line_id) AS po_line_id
              FROM inbound_receipt_lines AS rl
              GROUP BY rl.receipt_id, rl.item_id, rl.batch_code, rl.production_date
            )
            SELECT
              sl.ref,
              sl.ref_line,
              sl.warehouse_id,
              sl.item_id,
              sl.batch_code,
              sl.delta,
              sl.after_qty,
              sl.occurred_at,
              sl.production_date,
              sl.expiry_date,
              pol.line_no AS po_line_no
            FROM stock_ledger AS sl
            LEFT JOIN inbound_receipts AS r
              ON r.ref = sl.ref
             AND r.source_type = 'PO'
             AND r.source_id = :po_id
            LEFT JOIN rl_map AS m
              ON m.receipt_id = r.id
             AND m.item_id = sl.item_id
             AND m.batch_code = sl.batch_code
             AND m.production_date IS NOT DISTINCT FROM sl.production_date
            LEFT JOIN purchase_order_lines AS pol
              ON pol.id = m.po_line_id
            WHERE sl.reason = :reason
              AND sl.ref IN :refs
            ORDER BY sl.occurred_at ASC, sl.ref ASC, sl.ref_line ASC
            """
        )
        .bindparams(bindparam("refs", expanding=True))
    )

    res = await session.execute(
        stmt,
        {"po_id": int(po_id), "reason": reason, "refs": list(refs)},
    )
    rows = res.mappings().all()

    out: List[PurchaseOrderReceiptEventOut] = []
    for r in rows:
        item_id = int(r["item_id"])
        po_line_no = r.get("po_line_no")
        if po_line_no is None:
            po_line_no = fallback_line_no_map.get(item_id)

        out.append(
            PurchaseOrderReceiptEventOut(
                ref=str(r["ref"]),
                ref_line=int(r["ref_line"]),
                warehouse_id=int(r["warehouse_id"]),
                item_id=item_id,
                line_no=int(po_line_no) if po_line_no is not None else None,
                batch_code=str(r["batch_code"]),
                qty=int(r["delta"]),
                after_qty=int(r["after_qty"]),
                occurred_at=r["occurred_at"],
                production_date=r.get("production_date"),
                expiry_date=r.get("expiry_date"),
            )
        )

    return out
