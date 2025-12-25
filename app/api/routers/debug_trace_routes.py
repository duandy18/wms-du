# app/api/routers/debug_trace_routes.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.api.routers.debug_trace_helpers import filter_events_by_warehouse, infer_movement_type
from app.api.routers.debug_trace_schemas import TraceEventModel, TraceResponseModel
from app.services.trace_service import TraceService


def register(router: APIRouter) -> None:
    @router.get(
        "/trace/{trace_id}",
        response_model=TraceResponseModel,
    )
    async def get_trace(
        trace_id: str = Path(..., description="trace 唯一标识"),
        warehouse_id: Optional[int] = Query(
            None, description="可选：指定 warehouse_id 后，只保留该仓的事件，以及无仓的全局事件。"
        ),
        session: AsyncSession = Depends(get_session),
    ) -> TraceResponseModel:
        svc = TraceService(session)
        result = await svc.get_trace(trace_id)

        v2_events: List[TraceEventModel] = []

        for e in result.events:
            raw = e.raw or {}

            wh = raw.get("warehouse_id") or raw.get("warehouse") or raw.get("wh_id")
            item_id = raw.get("item_id")
            batch_code = raw.get("batch_code")

            reason_raw = raw.get("reason")
            reason = str(reason_raw) if reason_raw is not None else None
            if reason is not None and not reason.strip():
                reason = None

            movement_type = infer_movement_type(reason) if reason else None
            message = e.summary or reason or e.kind

            v2_events.append(
                TraceEventModel(
                    ts=e.ts,
                    source=e.source,
                    kind=e.kind,
                    ref=e.ref,
                    summary=e.summary,
                    raw=raw,
                    trace_id=trace_id,
                    warehouse_id=wh if isinstance(wh, int) else None,
                    item_id=item_id if isinstance(item_id, int) else None,
                    batch_code=batch_code if isinstance(batch_code, str) else None,
                    movement_type=movement_type,
                    message=message,
                    reason=reason,
                )
            )

        events = filter_events_by_warehouse(v2_events, warehouse_id)

        return TraceResponseModel(
            trace_id=trace_id,
            warehouse_id=warehouse_id,
            events=events,
        )
