# app/shipping_assist/billing/routes_reconcile.py

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session

from .contracts import (
    ReconcileShippingProviderBillCommand,
    ReconcileShippingProviderBillIn,
    ReconcileShippingProviderBillResult,
)
from .service import ShippingProviderBillReconcileService


def register(router: APIRouter) -> None:
    @router.post(
        "/reconcile",
        response_model=ReconcileShippingProviderBillResult,
    )
    async def reconcile_shipping_bill(
        payload: ReconcileShippingProviderBillIn,
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ReconcileShippingProviderBillResult:
        service = ShippingProviderBillReconcileService(session)

        return await service.reconcile(
            ReconcileShippingProviderBillCommand(
                shipping_provider_code=payload.shipping_provider_code,
            )
        )
