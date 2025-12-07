# app/api/routers/flow_replay.py

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.inventory_flow_service import InventoryFlowService
from app.services.ledger_replay_service import LedgerReplayService

router = APIRouter(prefix="/inventory", tags=["inventory-flow"])


@router.post("/flow-graph")
async def inventory_flow_graph(
    time_from: str,
    time_to: str,
    session: AsyncSession = Depends(get_session),
):
    svc = InventoryFlowService()
    g = await svc.build_graph(session, time_from=time_from, time_to=time_to)
    return {"ok": True, "graph": g}


@router.post("/ledger-replay")
async def ledger_replay(
    time_from: str,
    time_to: str,
    session: AsyncSession = Depends(get_session),
):
    svc = LedgerReplayService()
    rows = await svc.replay(session, time_from=time_from, time_to=time_to)
    return {"ok": True, "timeline": rows}
