# app/services/purchase_order_receipts.py
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_line import PurchaseOrderLine
from app.schemas.purchase_order_receipts import PurchaseOrderReceiptEventOut


async def _load_po_exists(session: AsyncSession, po_id: int) -> Optional[PurchaseOrder]:
    res = await session.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))
    return res.scalar_one_or_none()


async def _load_line_no_map(session: AsyncSession, po_id: int) -> Dict[int, int]:
    """
    item_id -> line_no
    - 若同一 item_id 在 PO 中出现多行（不推荐，但可能），取最小 line_no 保持稳定。
    """
    res = await session.execute(
        select(PurchaseOrderLine.item_id, PurchaseOrderLine.line_no)
        .where(PurchaseOrderLine.po_id == po_id)
    )
    rows: List[Tuple[int, int]] = [(int(r[0]), int(r[1])) for r in res.all()]
    m: Dict[int, int] = {}
    for item_id, line_no in rows:
        if item_id not in m:
            m[item_id] = line_no
        else:
            m[item_id] = min(m[item_id], line_no)
    return m


async def list_po_receipt_events(session: AsyncSession, po_id: int) -> List[PurchaseOrderReceiptEventOut]:
    """
    采购单历史收货事件（事实口径）：
    - 来自 stock_ledger：reason='RECEIPT' 且 ref='PO-{po_id}'
    - 按 ref_line 升序（与台账合同一致）
    """
    po = await _load_po_exists(session, po_id)
    if po is None:
        raise ValueError("PurchaseOrder not found")

    ref = f"PO-{po_id}"
    reason = "RECEIPT"

    line_no_map = await _load_line_no_map(session, po_id)

    res = await session.execute(
        text(
            """
            SELECT
              ref,
              ref_line,
              warehouse_id,
              item_id,
              batch_code,
              delta,
              after_qty,
              occurred_at,
              production_date,
              expiry_date
            FROM stock_ledger
            WHERE ref = :ref
              AND reason = :reason
            ORDER BY ref_line ASC
            """
        ),
        {"ref": ref, "reason": reason},
    )
    rows = res.mappings().all()

    out: List[PurchaseOrderReceiptEventOut] = []
    for r in rows:
        item_id = int(r["item_id"])
        out.append(
            PurchaseOrderReceiptEventOut(
                ref=str(r["ref"]),
                ref_line=int(r["ref_line"]),
                warehouse_id=int(r["warehouse_id"]),
                item_id=item_id,
                line_no=line_no_map.get(item_id),
                batch_code=str(r["batch_code"]),
                qty=int(r["delta"]),
                after_qty=int(r["after_qty"]),
                occurred_at=r["occurred_at"],
                production_date=r.get("production_date"),
                expiry_date=r.get("expiry_date"),
            )
        )
    return out
