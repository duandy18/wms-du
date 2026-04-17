from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.user.deps.auth import get_current_user
from app.wms.inbound_operations.contracts.inbound_task_read import (
    InboundTaskReadOut,
)
from app.wms.inbound_operations.contracts.operation_submit import (
    InboundOperationSubmitIn,
    InboundOperationSubmitOut,
)
from app.wms.inbound_operations.services.inbound_operation_submit_service import (
    submit_inbound_operation,
)
from app.wms.inbound_operations.services.inbound_task_read_service import (
    get_inbound_task,
)

router = APIRouter(prefix="/wms/inbound-operations", tags=["wms-inbound-operations"])


@router.get("/tasks/{receipt_no}", response_model=InboundTaskReadOut)
async def get_inbound_task_endpoint(
    receipt_no: str,
    session: AsyncSession = Depends(get_session),
) -> InboundTaskReadOut:
    try:
        return await get_inbound_task(session, receipt_no=receipt_no)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("", response_model=InboundOperationSubmitOut)
async def submit_inbound_operation_endpoint(
    payload: InboundOperationSubmitIn,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> InboundOperationSubmitOut:
    try:
        out = await submit_inbound_operation(
            session,
            payload=payload,
            operator_id=getattr(current_user, "id", None),
            operator_name=getattr(current_user, "username", None),
        )
        await session.commit()
        return out
    except NotImplementedError as e:
        await session.rollback()
        raise HTTPException(status_code=501, detail=str(e)) from e
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e


__all__ = ["router"]
