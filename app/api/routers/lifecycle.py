# app/api/routers/lifecycle.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.batch_lifeline_service import BatchLifelineService
from app.services.order_lifecycle_v2 import OrderLifecycleV2Service

router = APIRouter(prefix="/diagnostics/lifecycle", tags=["lifecycle"])


@router.get("/order-v2")
async def order_lifecycle_v2(
    trace_id: str = Query(
        ...,
        description="订单关联的 trace_id（统一生命周期视图只认 trace_id）",
    ),
    session: AsyncSession = Depends(get_session),
):
    """
    v2：基于 trace_id 的订单生命周期视图（官方推荐 / 唯一路线）。

    - 由 TraceService 聚合 event_store / audit_events / stock_ledger / orders / outbound_v2 等事件；
    - 再由 OrderLifecycleV2Service 按阶段推断：
        created / outbound / shipped / returned / delivered（以当前实现为准）
    - 同时给出整体 health + issues 诊断。
    """
    svc = OrderLifecycleV2Service(session)
    stages, summary = await svc.for_trace_id_with_summary(trace_id)

    return {
        "ok": True,
        "trace_id": trace_id,
        "stages": [s.__dict__ for s in stages],
        "summary": summary.__dict__,
    }


@router.get("/batch")
async def batch_lifeline(
    warehouse_id: int,
    item_id: int,
    batch_code: str,
    session: AsyncSession = Depends(get_session),
):
    """
    批次生命线（仍然按 wh + item + batch_code 维度走，和订单生命周期不同维度）。
    """
    svc = BatchLifelineService()
    lifeline = await svc.load_lifeline(
        session,
        warehouse_id=warehouse_id,
        item_id=item_id,
        batch_code=batch_code,
    )
    return {
        "ok": True,
        "lifeline": lifeline,
    }
