# app/tms/billing/routes_items.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

from .contracts import CarrierBillItemOut, CarrierBillItemsResponse
from .repository_items import list_carrier_bill_items


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-bills/items",
        response_model=CarrierBillItemsResponse,
    )
    async def get_shipping_bill_items(
        import_batch_no: str | None = Query(None),
        carrier_code: str | None = Query(None),
        tracking_no: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> CarrierBillItemsResponse:
        total, rows = await list_carrier_bill_items(
            session,
            import_batch_no=import_batch_no,
            carrier_code=carrier_code,
            tracking_no=tracking_no,
            limit=limit,
            offset=offset,
        )

        return CarrierBillItemsResponse(
            ok=True,
            rows=[CarrierBillItemOut(**r) for r in rows],
            total=total,
        )
