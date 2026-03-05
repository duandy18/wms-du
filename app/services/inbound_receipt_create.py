# app/services/inbound_receipt_create.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inbound_receipt import InboundReceipt
from app.services.purchase_order_queries import get_po_with_lines
from app.services.purchase_order_receive import get_or_create_po_draft_receipt_explicit
from app.services.purchase_order_time import UTC


async def create_po_draft_receipt(
    session: AsyncSession,
    *,
    po_id: int,
    occurred_at: Optional[datetime] = None,
) -> InboundReceipt:
    """
    Phase5：为 PO 创建/复用最新 DRAFT receipt（只写 Receipt 事实，不写库存）

    注意：Phase5+ 收敛后，不再依赖 purchase_order_receive._get_or_create_po_draft_receipt
    统一走显式 create/复用入口：get_or_create_po_draft_receipt_explicit
    """
    po = await get_po_with_lines(session, int(po_id), for_update=True)
    if po is None:
        raise ValueError(f"PurchaseOrder not found: id={po_id}")

    now = occurred_at or datetime.now(UTC)

    # 显式创建/复用 DRAFT receipt
    draft = await get_or_create_po_draft_receipt_explicit(session, po=po, occurred_at=now)
    return draft
