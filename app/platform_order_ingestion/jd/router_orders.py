# Module split: platform order ingestion now owns platform app config, auth, connection checks, native pull/ingest, and native order ledgers; no legacy alias is kept.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.platform_order_ingestion.jd.contracts_ledger import (
    JdOrderLedgerDetailEnvelopeOut,
    JdOrderLedgerListOut,
)
from app.platform_order_ingestion.jd.service_ledger import (
    get_jd_order_ledger_detail,
    list_jd_order_ledger_rows,
)
from app.oms.services.stores_helpers import check_perm

router = APIRouter(tags=["oms-jd-orders"])


@router.get("/jd/orders", response_model=JdOrderLedgerListOut)
async def list_jd_orders_ledger(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    check_perm(db, current_user, ["operations.outbound"])

    try:
        rows = await list_jd_order_ledger_rows(
            session,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to list jd order ledger: {exc}",
        ) from exc

    return JdOrderLedgerListOut(ok=True, data=rows)


@router.get("/jd/orders/{jd_order_id}", response_model=JdOrderLedgerDetailEnvelopeOut)
async def get_jd_order_ledger(
    jd_order_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    check_perm(db, current_user, ["operations.outbound"])

    try:
        detail = await get_jd_order_ledger_detail(
            session,
            jd_order_id=jd_order_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to load jd order ledger detail: {exc}",
        ) from exc

    if detail is None:
        raise HTTPException(status_code=404, detail="jd order not found")

    return JdOrderLedgerDetailEnvelopeOut(ok=True, data=detail)
