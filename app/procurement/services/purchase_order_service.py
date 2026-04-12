# app/wms/procurement/services/purchase_order_service.py
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.contracts.purchase_order import PurchaseOrderWithLinesOut
from app.procurement.contracts.purchase_order_receive_workbench import PurchaseOrderReceiveWorkbenchOut
from app.procurement.services.purchase_order_create import create_po_v2 as _create_po_v2
from app.procurement.services.purchase_order_presenter import build_po_with_lines_out
from app.procurement.repos.purchase_order_queries_repo import get_po_with_lines as _get_po_with_lines
from app.procurement.services.receive_po_line import receive_po_line as _receive_po_line
from app.procurement.services.purchase_order_receive_workbench import get_receive_workbench

UTC = timezone.utc


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

    async def receive_po_line(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        line_id: Optional[int] = None,
        line_no: Optional[int] = None,
        uom_id: int,
        qty: int,
        occurred_at: Optional[datetime] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        lot_code: Optional[str] = None,
        barcode: Optional[str] = None,
    ):
        return await _receive_po_line(
            session,
            po_id=po_id,
            line_id=line_id,
            line_no=line_no,
            uom_id=int(uom_id),
            qty=qty,
            occurred_at=occurred_at,
            production_date=production_date,
            expiry_date=expiry_date,
            lot_code=lot_code,
            barcode=barcode,
        )

    async def receive_po_line_workbench(
        self,
        session: AsyncSession,
        *,
        po_id: int,
        line_id: Optional[int] = None,
        line_no: Optional[int] = None,
        uom_id: int,
        qty: int,
        occurred_at: Optional[datetime] = None,
        production_date: Optional[date] = None,
        expiry_date: Optional[date] = None,
        lot_code: Optional[str] = None,
        barcode: Optional[str] = None,
    ) -> PurchaseOrderReceiveWorkbenchOut:
        await _receive_po_line(
            session,
            po_id=po_id,
            line_id=line_id,
            line_no=line_no,
            uom_id=int(uom_id),
            qty=qty,
            occurred_at=occurred_at,
            production_date=production_date,
            expiry_date=expiry_date,
            lot_code=lot_code,
            barcode=barcode,
        )

        return await get_receive_workbench(session, po_id=int(po_id))
