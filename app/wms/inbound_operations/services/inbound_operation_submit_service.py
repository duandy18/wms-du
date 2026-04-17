from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.wms.inbound_operations.contracts.operation_submit import (
    InboundOperationSubmitIn,
    InboundOperationSubmitOut,
)
from app.wms.inbound_operations.repos.inbound_operation_write_repo import (
    submit_inbound_operation_repo,
)


async def submit_inbound_operation(
    session: AsyncSession,
    *,
    payload: InboundOperationSubmitIn,
    operator_id: int | None = None,
    operator_name: str | None = None,
) -> InboundOperationSubmitOut:
    return await submit_inbound_operation_repo(
        session,
        payload=payload,
        operator_id=operator_id,
        operator_name=operator_name,
    )


__all__ = [
    "submit_inbound_operation",
]
