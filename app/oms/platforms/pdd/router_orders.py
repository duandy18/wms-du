from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_session
from app.db.deps import get_db
from app.oms.platforms.pdd.contracts_ledger import (
    PddOrderLedgerDetailEnvelopeOut,
    PddOrderLedgerListOut,
)
from app.oms.platforms.pdd.service_ledger import (
    get_pdd_order_ledger_detail,
    list_pdd_order_ledger_rows,
)
from app.oms.routers import stores as stores_router

router = APIRouter(tags=["oms-pdd-orders"])


@router.get("/pdd/orders", response_model=PddOrderLedgerListOut)
async def list_pdd_orders_ledger(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stores_router._check_perm(db, current_user, ["operations.outbound"])

    try:
        rows = await list_pdd_order_ledger_rows(
            session,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to list pdd order ledger: {exc}",
        ) from exc

    return PddOrderLedgerListOut(ok=True, data=rows)


@router.get("/pdd/orders/{pdd_order_id}", response_model=PddOrderLedgerDetailEnvelopeOut)
async def get_pdd_order_ledger(
    pdd_order_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    stores_router._check_perm(db, current_user, ["operations.outbound"])

    try:
        detail = await get_pdd_order_ledger_detail(
            session,
            pdd_order_id=pdd_order_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to load pdd order ledger detail: {exc}",
        ) from exc

    if detail is None:
        raise HTTPException(status_code=404, detail="pdd order not found")

    return PddOrderLedgerDetailEnvelopeOut(ok=True, data=detail)
