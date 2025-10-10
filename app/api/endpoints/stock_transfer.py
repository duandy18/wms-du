# app/api/endpoints/stock_transfer.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.stock import StockTransferIn, StockTransferMove, StockTransferOut
from app.services.stock_service import StockService

router = APIRouter(prefix="/stock/transfer", tags=["stock"])


@router.post("", response_model=StockTransferOut)
async def transfer_stock(
    body: StockTransferIn,
    session: AsyncSession = Depends(get_session),
) -> StockTransferOut:
    svc = StockService()
    res = await svc.transfer(
        session=session,
        item_id=body.item_id,
        src_location_id=body.src_location_id,
        dst_location_id=body.dst_location_id,
        qty=body.qty,
        allow_expired=body.allow_expired,
        reason=body.reason,
        ref=body.ref,
    )
    return StockTransferOut(
        item_id=res["item_id"],
        src_location_id=res["src_location_id"],
        dst_location_id=res["dst_location_id"],
        total_moved=res["total_moved"],
        moves=[StockTransferMove(**m) for m in res["moves"]],
    )
