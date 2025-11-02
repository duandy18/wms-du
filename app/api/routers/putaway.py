# app/api/routers/putaway.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.putaway_service import PutawayService

router = APIRouter(prefix="/putaway", tags=["putaway"])


class PutawayIn(BaseModel):
    item_id: int = Field(..., ge=1)
    from_location_id: int = Field(..., ge=0, description="来源库位，STAGE 可用 0/约定位")
    to_location_id: int = Field(..., ge=1)
    qty: int = Field(..., ge=1)
    ref: str
    ref_line: Optional[int] = None  # 若传字符串可在服务层自行处理/或用约定CRC


class PutawayOut(BaseModel):
    status: str = "ok"
    moved: int


@router.post("", response_model=PutawayOut)
async def putaway(
    body: PutawayIn,
    session: AsyncSession = Depends(get_session),
):
    """
    上架：调用 PutawayService.putaway()
    - 负库存/来源不足 → 409
    - 成功返回 moved 数量
    """
    try:
        res = await PutawayService.putaway(
            session=session,
            item_id=body.item_id,
            from_location_id=body.from_location_id,
            to_location_id=body.to_location_id,
            qty=body.qty,
            ref=body.ref,
            ref_line=(body.ref_line if isinstance(body.ref_line, int) else None),
            occurred_at=datetime.now(UTC),
        )
        await session.commit()
        return PutawayOut(status=res.get("status", "ok"), moved=res.get("moved", body.qty))
    except ValueError as e:
        await session.rollback()
        # 例如 NEGATIVE_STOCK / 来源不足等
        raise HTTPException(status_code=409, detail=str(e) or "NEGATIVE_STOCK")
