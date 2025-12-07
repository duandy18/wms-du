# app/api/routers/stock_rebuild.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.rebuild_service import RebuildService

router = APIRouter(prefix="/stock/rebuild", tags=["stock_rebuild"])


@router.post("/ledger")
async def rebuild_from_ledger(
    time_from: str | None = None,
    time_to: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """
    从台账重建库存（stocks）。
    """
    svc = RebuildService()
    res = await svc.rebuild_stocks(
        session,
        time_from=time_from,
        time_to=time_to,
    )
    return {"ok": True, "rebuild": res}
