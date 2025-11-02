# app/api/routers/count.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.stock_service import StockService

router = APIRouter(prefix="/count", tags=["count"])


class CountIn(BaseModel):
    item_id: int = Field(..., ge=1)
    location_id: int = Field(..., ge=0)
    counted_qty: int = Field(..., ge=0, description="实盘数量")
    ref: str = Field(..., description="扫描/审计引用号")
    apply: bool = Field(False, description="True=真动作落账；False=探活（不落账）")


class CountOut(BaseModel):
    item_id: int
    location_id: int
    delta: int
    after_qty: Optional[int] = None
    applied: bool


@router.post("", response_model=CountOut)
async def count_reconcile(
    body: CountIn,
    session: AsyncSession = Depends(get_session),
):
    """
    盘点：对某库位/物料执行 reconcile_inventory()
    - apply=False 探活（回滚，不留痕）
    - apply=True 真动作（提交，写台账）
    """
    svc = StockService()
    res = await svc.reconcile_inventory(
        session=session,
        item_id=body.item_id,
        location_id=body.location_id,
        counted_qty=body.counted_qty,
        apply=body.apply,
        ref=body.ref,
    )
    if body.apply:
        await session.commit()
    else:
        await session.rollback()

    return CountOut(
        item_id=body.item_id,
        location_id=body.location_id,
        delta=int(res.get("delta", 0)),
        after_qty=(int(res["after_qty"]) if res.get("after_qty") is not None else None),
        applied=bool(body.apply),
    )
