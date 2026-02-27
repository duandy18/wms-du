from __future__ import annotations

from typing import Set

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.batch_code_contract import (
    fetch_item_expiry_policy_map,
    validate_batch_code_contract,
)
from app.db.session import get_session
from app.schemas.internal_outbound import (
    InternalOutboundDocOut,
    InternalOutboundUpsertLineIn,
)
from app.services.internal_outbound_service import InternalOutboundService

router = APIRouter(prefix="/internal-outbound", tags=["internal-outbound"])

svc = InternalOutboundService()


def _requires_batch_from_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


@router.post("/docs/{doc_id}/lines", response_model=InternalOutboundDocOut)
async def upsert_internal_outbound_line(
    doc_id: int,
    payload: InternalOutboundUpsertLineIn,
    session: AsyncSession = Depends(get_session),
) -> InternalOutboundDocOut:
    try:
        # ✅ Phase M：改用 expiry_policy
        item_ids: Set[int] = {int(payload.item_id)}
        expiry_policy_map = await fetch_item_expiry_policy_map(session, item_ids)

        if payload.item_id not in expiry_policy_map:
            raise HTTPException(status_code=422, detail=f"unknown item_id: {payload.item_id}")

        requires_batch = _requires_batch_from_expiry_policy(
            expiry_policy_map.get(payload.item_id)
        )

        batch_code = validate_batch_code_contract(
            requires_batch=requires_batch,
            batch_code=payload.batch_code,
        )

        await svc.upsert_line(
            session,
            doc_id=doc_id,
            item_id=payload.item_id,
            qty=payload.qty,
            batch_code=batch_code,
            uom=payload.uom,
            note=payload.note,
        )
        await session.commit()

        doc = await svc.get_with_lines(session, doc_id)
        return InternalOutboundDocOut.model_validate(doc)

    except ValueError as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
