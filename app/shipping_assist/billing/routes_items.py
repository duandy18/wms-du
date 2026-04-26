# app/shipping_assist/billing/routes_items.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session

from .contracts import ShippingProviderBillItemOut, ShippingProviderBillItemsResponse
from .repository_items import list_carrier_bill_items


def register(router: APIRouter) -> None:
    @router.get(
        "/items",
        response_model=ShippingProviderBillItemsResponse,
    )
    async def get_shipping_bill_items(
        shipping_provider_code: str | None = Query(None),
        tracking_no: str | None = Query(None),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ShippingProviderBillItemsResponse:
        total, rows = await list_carrier_bill_items(
            session,
            shipping_provider_code=shipping_provider_code,
            tracking_no=tracking_no,
            limit=limit,
            offset=offset,
        )

        return ShippingProviderBillItemsResponse(
            ok=True,
            rows=[ShippingProviderBillItemOut(**r) for r in rows],
            total=total,
        )
