# app/api/routers/snapshot_v3.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.snapshot_v3_service import SnapshotV3Service

router = APIRouter(prefix="/stock/snapshot/v3", tags=["snapshot_v3"])


@router.post("/cut")
async def snapshot_cut(
    at: datetime,
    session: AsyncSession = Depends(get_session),
):
    svc = SnapshotV3Service()
    res = await svc.snapshot_cut(session, at=at)
    return {"ok": True, "result": res}


@router.post("/rebuild")
async def snapshot_rebuild(
    at: datetime,
    session: AsyncSession = Depends(get_session),
):
    svc = SnapshotV3Service()
    res = await svc.rebuild_snapshot_from_ledger(session, snapshot_date=at)
    return {"ok": True, "result": res}


@router.post("/compare")
async def snapshot_compare(
    at: datetime,
    session: AsyncSession = Depends(get_session),
):
    svc = SnapshotV3Service()
    res = await svc.compare_snapshot(session, snapshot_date=at)
    return {"ok": True, "result": res}
