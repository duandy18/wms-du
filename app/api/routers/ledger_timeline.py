# app/api/routers/ledger_timeline.py
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import normalize_optional_batch_code
from app.db.session import get_session
from app.services.ledger_timeline_service import LedgerTimelineService

router = APIRouter(prefix="/stock/ledger/timeline", tags=["ledger_timeline"])


@router.post("")
async def ledger_timeline(
    time_from: datetime,
    time_to: datetime,
    warehouse_id: int | None = None,
    item_id: int | None = None,
    batch_code: str | None = None,
    trace_id: str | None = None,
    ref: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    # ✅ 主线 B：查询级 batch_code 归一（None/空串/'None' -> None）
    batch_code_norm = normalize_optional_batch_code(batch_code)

    svc = LedgerTimelineService()
    rows = await svc.fetch_timeline(
        session,
        time_from=time_from,
        time_to=time_to,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code_norm,
        trace_id=trace_id,
        ref=ref,
    )
    return {"ok": True, "rows": rows}
