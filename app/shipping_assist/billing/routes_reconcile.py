# app/shipping_assist/billing/routes_reconcile.py

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session

from .contracts import (
    ReconcileCarrierBillCommand,
    ReconcileCarrierBillIn,
    ReconcileCarrierBillResult,
)
from .service import CarrierBillReconcileService


def register(router: APIRouter) -> None:
    @router.post(
        "/reconcile",
        response_model=ReconcileCarrierBillResult,
    )
    async def reconcile_shipping_bill(
        payload: ReconcileCarrierBillIn,
        session: AsyncSession = Depends(get_session),
        _current_user: Any = Depends(get_current_user),
    ) -> ReconcileCarrierBillResult:
        service = CarrierBillReconcileService(session)

        return await service.reconcile(
            ReconcileCarrierBillCommand(
                carrier_code=payload.carrier_code,
            )
        )
