# app/api/routers/count.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, conint, confloat
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.services.stock_service import StockService

router = APIRouter(prefix="/count", tags=["count"])


class CountCommitIn(BaseModel):
    item_id: conint(gt=0) = Field(..., description="被盘点的物料 ID")
    location_id: conint(gt=0) = Field(..., description="被盘点的库位 ID")
    counted_qty: confloat(ge=0) = Field(..., description="实盘数量（非差额）")
    apply: bool = Field(False, description="是否真实落账（False=探活试算）")
    ref: str | None = Field(None, description="幂等/追踪用引用号，可选")


class CountCommitOut(BaseModel):
    ref: str
    diff: float | None = None
    reconciled: bool
    message: str | None = None


@router.post("/commit", response_model=CountCommitOut)
async def count_commit(
    body: CountCommitIn,
    session: AsyncSession = Depends(get_session),
) -> CountCommitOut:
    """
    盘点：对某库位/物料执行 reconcile_inventory()
    - apply=False：只试算差额，不落账
    - apply=True ：按差额调整库存并记账
    """
    svc = StockService()

    # 直接按新签名调用：counted_qty（不是 qty），其余参数保持一致
    try:
        res = await svc.reconcile_inventory(
            session=session,
            item_id=body.item_id,
            location_id=body.location_id,
            counted_qty=float(body.counted_qty),
            apply=bool(body.apply),
            ref=body.ref,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"reconcile failed: {e!s}")

    return CountCommitOut(
        ref=res.get("ref") or (body.ref or ""),
        diff=res.get("diff"),
        reconciled=bool(res.get("reconciled") or body.apply),
        message=res.get("message"),
    )
