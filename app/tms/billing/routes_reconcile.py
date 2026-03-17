# app/tms/billing/routes_reconcile.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_session

from .contracts import (
    ReconcileCarrierBillCommand,
    ReconcileCarrierBillIn,
    ReconcileCarrierBillResult,
)
from .service import CarrierBillReconcileService


def register(router: APIRouter) -> None:
    @router.post(
        "/shipping-bills/reconcile",
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
                import_batch_id=payload.import_batch_id,
            )
        )
