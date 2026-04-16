# app/procurement/services/purchase_order_service.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.contracts.purchase_order import PurchaseOrderWithLinesOut
from app.procurement.services.purchase_order_create import create_po_v2 as _create_po_v2
from app.procurement.services.purchase_order_update import update_po_v2 as _update_po_v2
from app.procurement.services.purchase_order_presenter import build_po_with_lines_out
from app.procurement.repos.purchase_order_queries_repo import get_po_with_lines as _get_po_with_lines



class PurchaseOrderService:
    """
    采购单服务（Phase 2：唯一形态）
    """

    def __init__(self) -> None:
        pass

    async def create_po_v2(
        self,
        session: AsyncSession,
        *,
        supplier_id: int,
        warehouse_id: int,
        purchaser: str,
        purchase_time: datetime,
        remark: Optional[str] = None,
        lines: List[Dict[str, Any]],
    ):
        return await _create_po_v2(
            session,
            supplier_id=int(supplier_id),
            warehouse_id=warehouse_id,
            purchaser=purchaser,
            purchase_time=purchase_time,
            remark=remark,
            lines=lines,
        )

    async def update_po_v2(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        supplier_id: int,
        warehouse_id: int,
        purchaser: str,
        purchase_time: datetime,
        remark: Optional[str] = None,
        lines: List[Dict[str, Any]],
    ):
        return await _update_po_v2(
            session,
            po_id=int(po_id),
            supplier_id=int(supplier_id),
            warehouse_id=warehouse_id,
            purchaser=purchaser,
            purchase_time=purchase_time,
            remark=remark,
            lines=lines,
        )

    async def get_po_with_lines(
        self,
        session: AsyncSession,
        po_id: int,
        *,
        for_update: bool = False,
    ) -> Optional[PurchaseOrderWithLinesOut]:
        po = await _get_po_with_lines(session, po_id, for_update=for_update)
        if po is None:
            return None

        try:
            await session.refresh(
                po,
                attribute_names=[
                    "status",
                    "last_received_at",
                    "closed_at",
                    "close_reason",
                    "close_note",
                    "closed_by",
                    "canceled_at",
                    "canceled_reason",
                    "canceled_by",
                ],
            )
        except Exception:
            pass

        return await build_po_with_lines_out(session, po)
