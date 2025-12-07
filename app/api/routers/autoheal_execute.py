# app/api/routers/autoheal_execute.py

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.inventory_autoheal_execute import InventoryAutoHealExecutor

router = APIRouter(prefix="/inventory/autoheal", tags=["inventory_autoheal_execute"])


@router.post("/execute")
async def autoheal_execute(
    cut: str,
    dry_run: bool = True,
    session: AsyncSession = Depends(get_session),
):
    svc = InventoryAutoHealExecutor()
    return await svc.execute(session, cut=cut, dry_run=dry_run)
