from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.user.deps.auth import get_current_user
from app.db.deps import get_async_session as get_session
from app.db.deps import get_db
from app.oms.platforms.taobao.contracts_ledger import (
    TaobaoOrderLedgerDetailEnvelopeOut,
    TaobaoOrderLedgerListOut,
)
from app.oms.platforms.taobao.service_ledger import (
    get_taobao_order_ledger_detail,
    list_taobao_order_ledger_rows,
)
from app.oms.services.stores_helpers import check_perm

router = APIRouter(tags=["oms-taobao-orders"])


@router.get("/taobao/orders", response_model=TaobaoOrderLedgerListOut)
async def list_taobao_orders_ledger(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    check_perm(db, current_user, ["operations.outbound"])

    try:
        rows = await list_taobao_order_ledger_rows(
            session,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to list taobao order ledger: {exc}",
        ) from exc

    return TaobaoOrderLedgerListOut(ok=True, data=rows)


@router.get("/taobao/orders/{taobao_order_id}", response_model=TaobaoOrderLedgerDetailEnvelopeOut)
async def get_taobao_order_ledger(
    taobao_order_id: int = Path(..., ge=1),
    session: AsyncSession = Depends(get_session),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    check_perm(db, current_user, ["operations.outbound"])

    try:
        detail = await get_taobao_order_ledger_detail(
            session,
            taobao_order_id=taobao_order_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"failed to load taobao order ledger detail: {exc}",
        ) from exc

    if detail is None:
        raise HTTPException(status_code=404, detail="taobao order not found")

    return TaobaoOrderLedgerDetailEnvelopeOut(ok=True, data=detail)
