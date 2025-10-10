# app/api/endpoints/stock_maintenance.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.stock import TransferExpiredIn, TransferExpiredMove, TransferExpiredOut
from app.services.stock_service import StockService

router = APIRouter(prefix="/stock/maintenance", tags=["stock"])


@router.post("/expired/transfer", response_model=TransferExpiredOut)
async def transfer_expired(
    body: TransferExpiredIn,
    session: AsyncSession = Depends(get_session),
) -> TransferExpiredOut:
    svc = StockService()
    result = await svc.auto_transfer_expired(
        session=session,
        warehouse_id=body.warehouse_id,
        to_location_id=body.to_location_id,
        to_location_name=body.to_location_name,
        item_ids=body.item_ids,
        dry_run=body.dry_run,
        reason="EXPIRED_TRANSFER",
        ref="SYS-AUTO",
    )
    return TransferExpiredOut(
        warehouse_id=result["warehouse_id"],
        moved_total=result["moved_total"],
        moves=[TransferExpiredMove(**m) for m in result["moves"]],
    )
