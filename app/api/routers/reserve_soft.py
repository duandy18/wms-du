# app/api/routers/reserve_soft.py
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.core.audit import new_trace
from app.schemas.reserve_soft import ReservePersistIn, ReservePickIn, ReserveReleaseIn
from app.services.soft_reserve_service import SoftReserveService

router = APIRouter(prefix="/reserve", tags=["reserve-soft"])


@router.post("/persist", operation_id="reserve_persist_soft")
async def reserve_persist(
    payload: ReservePersistIn,
    session: AsyncSession = Depends(get_session),
):
    svc = SoftReserveService()
    _trace = new_trace("http:/reserve/persist")
    result = await svc.persist(
        session,
        platform=payload.platform,
        shop_id=payload.shop_id,
        warehouse_id=int(payload.warehouse_id),
        ref=payload.ref,
        lines=[{"item_id": line.item_id, "qty": line.qty} for line in payload.lines],
        expire_at=payload.expire_at,
    )
    return result


@router.post("/pick/commit", operation_id="reserve_pick_soft")
async def reserve_pick(
    payload: ReservePickIn,
    session: AsyncSession = Depends(get_session),
):
    svc = SoftReserveService()
    _trace = new_trace("http:/reserve/pick/commit")
    result = await svc.pick_consume(
        session,
        platform=payload.platform,
        shop_id=payload.shop_id,
        warehouse_id=int(payload.warehouse_id),
        ref=payload.ref,
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
    )
    return result


@router.post("/release", operation_id="reserve_release_soft")
async def reserve_release(
    payload: ReserveReleaseIn,
    session: AsyncSession = Depends(get_session),
):
    svc = SoftReserveService()
    _trace = new_trace("http:/reserve/release")
    result = await svc.release(
        session,
        platform=payload.platform,
        shop_id=payload.shop_id,
        warehouse_id=int(payload.warehouse_id),
        ref=payload.ref,
    )
    return result
