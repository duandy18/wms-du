# app/wms/analysis/routers/ledger_reconcile_v2.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.wms.analysis.services.multi_reconcile_service import MultiReconcileService

router = APIRouter(prefix="/stock/ledger/reconcile-v2", tags=["ledger_reconcile_v2"])


class ReconcileSummaryPayload(BaseModel):
    time_from: datetime | None = None
    time_to: datetime | None = None


class ThreeBooksPayload(BaseModel):
    cut: datetime


def _normalize_time_range(
    time_from: datetime | None,
    time_to: datetime | None,
) -> Tuple[datetime, datetime]:
    """
    与 stock_ledger 路由保持一致：

    - 两者都为空：默认最近 7 天；
    - 只填了一个：自动补另一个；
    - 限制最大跨度 90 天，避免误查全库。
    """
    now = datetime.now(timezone.utc)

    t_to = time_to or now
    t_from = time_from or (t_to - timedelta(days=7))

    if t_to < t_from:
        raise HTTPException(status_code=400, detail="'time_to' must be >= 'time_from'")

    max_span = timedelta(days=90)
    if t_to - t_from > max_span:
        raise HTTPException(
            status_code=400,
            detail="时间范围过大，请缩小到 90 天以内（<= 90 天）。",
        )

    return t_from, t_to


@router.post("/summary")
async def reconcile_summary(
    payload: ReconcileSummaryPayload,
    session: AsyncSession = Depends(get_session),
):
    """
    多维对账汇总（供 LedgerCockpit 使用）：
    """
    svc = MultiReconcileService()

    time_from, time_to = _normalize_time_range(
        payload.time_from,
        payload.time_to,
    )

    return {
        "movement_type": await svc.movement_type_summary(
            session, time_from=time_from, time_to=time_to
        ),
        "ref": await svc.ref_summary(session, time_from=time_from, time_to=time_to),
        "trace": await svc.trace_summary(session, time_from=time_from, time_to=time_to),
    }


@router.post("/three-books")
async def reconcile_three_books(
    payload: ThreeBooksPayload,
    session: AsyncSession = Depends(get_session),
):
    """
    三账对账入口：
    """
    svc = MultiReconcileService()
    cut = payload.cut

    books = await svc.three_books_compare(session, cut=cut)

    return {
        "cut": cut.isoformat(),
        "books": books,
    }
