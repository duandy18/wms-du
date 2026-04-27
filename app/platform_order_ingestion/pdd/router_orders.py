# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.pdd.contracts_ledger import (
    PddOrderLedgerDetailEnvelopeOut,
    PddOrderLedgerListOut,
)
from app.platform_order_ingestion.pdd.service_ledger import (
    get_pdd_order_ledger_detail,
    list_pdd_order_ledger_rows,
)
from app.platform_order_ingestion.permissions import require_platform_order_ingestion_read

router = APIRouter(tags=["oms-pdd-orders"])


@router.get("/pdd/orders", response_model=PddOrderLedgerListOut)
async def list_pdd_orders_ledger(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_platform_order_ingestion_read(db, current_user)

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
    require_platform_order_ingestion_read(db, current_user)

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
