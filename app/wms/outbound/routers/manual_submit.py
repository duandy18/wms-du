# app/wms/outbound/routers/manual_submit.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.db.deps import get_async_session as get_session
from app.user.deps.auth import get_current_user
from app.wms.outbound.contracts.manual_submit import (
    ManualOutboundSubmitIn,
    ManualOutboundSubmitOut,
)
from app.wms.outbound.services.outbound_event_submit_service import (
    submit_manual_outbound_event,
)

router = APIRouter(prefix="/wms/outbound", tags=["wms-outbound-manual-submit"])


@router.post(
    "/manual/{doc_id}/submit",
    response_model=ManualOutboundSubmitOut,
)
async def submit_manual_outbound(
    doc_id: int,
    payload: ManualOutboundSubmitIn,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> ManualOutboundSubmitOut:
    trace = new_trace("http:/wms/outbound/manual/submit")

    result = await submit_manual_outbound_event(
        session,
        doc_id=int(doc_id),
        operator_id=getattr(user, "id", None),
        trace_id=trace.trace_id,
        payload=payload,
    )
    await session.commit()
    return result
