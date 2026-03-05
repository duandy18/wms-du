# app/api/routers/purchase_reports_routes_daily.py
from __future__ import annotations

from typing import List, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.inbound_receipt import InboundReceipt, InboundReceiptLine
from app.schemas.purchase_report import DailyPurchaseReportItem


def register(router: APIRouter) -> None:
    @router.get("/daily", response_model=List[DailyPurchaseReportItem])
    async def purchase_report_daily(
        session: AsyncSession = Depends(get_session),
        mode: Literal["fact", "plan"] = Query("fact"),
    ) -> List[DailyPurchaseReportItem]:

        if mode == "fact":
            stmt = (
                session.query(
                    func.date(InboundReceipt.occurred_at).label("day"),
                    func.coalesce(func.sum(InboundReceiptLine.qty_base), 0).label("total_units"),
                )
                .join(InboundReceiptLine, InboundReceiptLine.receipt_id == InboundReceipt.id)
                .filter(InboundReceipt.status == "CONFIRMED")
                .group_by(func.date(InboundReceipt.occurred_at))
                .order_by(func.date(InboundReceipt.occurred_at))
            )

            rows = await session.execute(stmt.statement)
            return [
                DailyPurchaseReportItem(
                    day=r[0],
                    order_count=None,
                    total_units=int(r[1] or 0),
                    total_amount=None,
                )
                for r in rows
            ]

        return []
