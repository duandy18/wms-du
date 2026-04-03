# app/wms/procurement/routers/purchase_reports_routes_suppliers.py
from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.wms.procurement.contracts.purchase_report import SupplierPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/suppliers", response_model=List[SupplierPurchaseReportItem])
    async def purchase_report_by_suppliers(
        session: AsyncSession = Depends(get_session),
        mode: Literal["fact", "plan"] = Query("fact"),
    ) -> List[SupplierPurchaseReportItem]:

        if mode == "fact":
            stmt = (
                session.query(
                    InboundReceipt.supplier_id,
                    func.count(distinct(InboundReceipt.source_id)).label("order_count"),
                    func.coalesce(func.sum(InboundReceiptLine.qty_base), 0).label("total_units"),
                )
                .join(InboundReceiptLine, InboundReceiptLine.receipt_id == InboundReceipt.id)
                .filter(InboundReceipt.status == "CONFIRMED")
                .group_by(InboundReceipt.supplier_id)
            )

            rows = await session.execute(stmt.statement)
            return [
                SupplierPurchaseReportItem(
                    supplier_id=r[0],
                    supplier_name=None,
                    order_count=int(r[1] or 0),
                    total_units=int(r[2] or 0),
                    total_amount=None,
                    avg_unit_price=None,
                )
                for r in rows
            ]

        return []
