# app/api/routers/stock_ledger_routes_query_history.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.stock_ledger import StockLedger
from app.schemas.stock_ledger import LedgerList, LedgerQuery, LedgerRow
from app.api.routers.stock_ledger_helpers import build_base_ids_stmt, infer_movement_type

UTC = timezone.utc
MAX_HISTORY_DAYS = 3650  # 10 years


def _has_anchor(q: LedgerQuery) -> bool:
    """
    历史查询锚点：
    - trace_id/ref 最强
    - item_id 次强
    - reason_canon/sub_reason 也允许作为锚点（配合时间窗）
    """
    if q.trace_id and str(q.trace_id).strip():
        return True
    if q.ref and str(q.ref).strip():
        return True
    if q.item_id is not None:
        return True

    rc = getattr(q, "reason_canon", None)
    if rc is not None and str(rc).strip():
        return True

    sr = getattr(q, "sub_reason", None)
    if sr is not None and str(sr).strip():
        return True

    return False


def _normalize_history_time_range(q: LedgerQuery) -> tuple[datetime, datetime]:
    """
    历史查询时间窗：
    - 必须提供 time_from（避免无界全表扫）
    - time_to 可选，不填则 now
    - 最大跨度 MAX_HISTORY_DAYS（默认 10 年）
    """
    if q.time_from is None:
        raise HTTPException(status_code=400, detail="历史查询必须指定 time_from。")

    t1 = q.time_from
    t2 = q.time_to or datetime.now(UTC)

    if t1.tzinfo is None:
        t1 = t1.replace(tzinfo=UTC)
    if t2.tzinfo is None:
        t2 = t2.replace(tzinfo=UTC)

    if t2 < t1:
        raise HTTPException(status_code=400, detail="time_to 不能早于 time_from。")

    if (t2 - t1) > timedelta(days=MAX_HISTORY_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"时间范围过大，请缩小到 {MAX_HISTORY_DAYS} 天以内。",
        )

    return t1, t2


def register(router: APIRouter) -> None:
    @router.post("/query-history", response_model=LedgerList)
    async def query_ledger_history(
        payload: LedgerQuery,
        session: AsyncSession = Depends(get_session),
    ) -> LedgerList:
        """
        历史台账查询（用于 >90 天窗口）：

        - 必须提供 time_from；
        - 必须提供锚点（trace_id/ref/item_id/reason_canon/sub_reason 任意一项）；
        - 返回结构与 /stock/ledger/query 一致（LedgerList）。
        """
        if not _has_anchor(payload):
            raise HTTPException(
                status_code=400,
                detail="历史查询必须至少指定：trace_id / ref / item_id / reason_canon / sub_reason（任意一项）。",
            )

        time_from, time_to = _normalize_history_time_range(payload)

        # 复用基础过滤（已经包含 reason_canon / sub_reason / reason / ref / trace_id 等）
        ids_stmt = build_base_ids_stmt(payload, time_from, time_to)
        ids_subq = ids_stmt.subquery()

        total = (await session.execute(select(func.count()).select_from(ids_subq))).scalar_one()

        list_stmt = (
            select(StockLedger)
            .where(StockLedger.id.in_(select(ids_subq.c.id)))
            .order_by(StockLedger.occurred_at.desc(), StockLedger.id.desc())
            .limit(payload.limit)
            .offset(payload.offset)
        )
        rows = (await session.execute(list_stmt)).scalars().all()

        return LedgerList(
            total=total,
            items=[
                LedgerRow(
                    id=r.id,
                    delta=r.delta,
                    reason=r.reason,
                    reason_canon=getattr(r, "reason_canon", None),
                    sub_reason=getattr(r, "sub_reason", None),
                    ref=r.ref,
                    ref_line=r.ref_line,
                    occurred_at=r.occurred_at,
                    created_at=r.created_at,
                    after_qty=r.after_qty,
                    item_id=r.item_id,
                    item_name=getattr(r, "item_name", None),
                    warehouse_id=r.warehouse_id,
                    batch_code=r.batch_code,
                    trace_id=r.trace_id,
                    movement_type=infer_movement_type(r.reason),
                )
                for r in rows
            ],
        )
