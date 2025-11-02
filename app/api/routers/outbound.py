# app/api/routers/outbound.py
from __future__ import annotations

import os
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.stock import Stock
from app.services.outbound_service import commit_outbound  # 复用服务层扣减/记账

router = APIRouter(prefix="/outbound", tags=["outbound"])


class OutboundLine(BaseModel):
    item_id: int
    location_id: int
    qty: int = Field(ge=1)
    ref_line: str | int | None = None


class OutboundCommitIn(BaseModel):
    ref: str
    lines: list[OutboundLine]


@router.post("/commit")
async def outbound_commit(payload: OutboundCommitIn, session: AsyncSession = Depends(get_session)):
    outbound_atomic = os.getenv("OUTBOUND_ATOMIC", "false").lower() == "true"

    if outbound_atomic:
        need: dict[tuple[int, int], int] = defaultdict(int)
        pairs: set[tuple[int, int]] = set()
        for ln in payload.lines:
            key = (int(ln.item_id), int(ln.location_id))
            need[key] += int(ln.qty)
            pairs.add(key)

        if pairs:
            rows = await session.execute(
                select(Stock.item_id, Stock.location_id, Stock.qty).where(
                    tuple_(Stock.item_id, Stock.location_id).in_(list(pairs))
                )
            )
            have_map: dict[tuple[int, int], int] = {
                (int(item_id_val), int(loc_id_val)): int(q or 0)
                for item_id_val, loc_id_val, q in rows.all()
            }
            for (item_id_val, loc_id_val), required in need.items():
                have = have_map.get((item_id_val, loc_id_val), 0)
                if have < required:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "INSUFFICIENT_STOCK",
                            "item_id": item_id_val,
                            "location_id": loc_id_val,
                            "required": required,
                            "have": have,
                        },
                    )

    results = await commit_outbound(
        session=session,
        ref=payload.ref,
        lines=[ln.model_dump() for ln in payload.lines],
    )
    return {"ref": payload.ref, "results": results}
