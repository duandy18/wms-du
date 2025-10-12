from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_async_session
from app.schemas.inbound import BarcodeScanIn, InboundReceiveIn, PutawayIn, InboundOut, PutawayOut
from app.services.barcode import BarcodeResolver
from app.services.inbound_service import InboundService
from sqlalchemy.exc import IntegrityError

router = APIRouter(prefix="/inbound", tags=["inbound"])
resolver = BarcodeResolver()
svc = InboundService()

@router.post("/scan")
async def scan_barcode(payload: BarcodeScanIn):
    sku = resolver.resolve(payload.barcode)
    if not sku:
        raise HTTPException(status_code=400, detail="INVALID_BARCODE")
    return {"sku": sku, "qty": payload.qty or 1}

@router.post("/receive", response_model=InboundOut)
async def inbound_receive(payload: InboundReceiveIn, session: AsyncSession = Depends(get_async_session)):
    try:
        async with session.begin():
            data = await svc.receive(
                session,
                sku=payload.sku, qty=payload.qty,
                batch_code=payload.batch_code,
                production_date=payload.production_date,
                expiry_date=payload.expiry_date,
                ref=payload.ref, ref_line=payload.ref_line
            )
        return data
    except ValueError as e:
        if str(e) == "BATCH_EXPIRY_CONFLICT":
            raise HTTPException(status_code=422, detail="BATCH_EXPIRY_CONFLICT")
        if str(e) == "SKU_NOT_FOUND":
            raise HTTPException(status_code=404, detail="SKU_NOT_FOUND")
        raise
    except IntegrityError:
        # 幂等重复：ref+ref_line 冲突
        raise HTTPException(status_code=409, detail="DUPLICATE_REF_LINE")

@router.post("/putaway", response_model=PutawayOut)
async def inbound_putaway(payload: PutawayIn, session: AsyncSession = Depends(get_async_session)):
    try:
        async with session.begin():
            data = await svc.putaway(
                session,
                sku=payload.sku, batch_code=payload.batch_code,
                qty=payload.qty, to_location_id=payload.to_location_id,
                ref=payload.ref, ref_line=payload.ref_line
            )
        return data
    except ValueError as e:
        msg = str(e)
        if msg in ("SKU_NOT_FOUND", "BATCH_NOT_FOUND"):
            raise HTTPException(status_code=404, detail=msg)
        if msg == "NEGATIVE_STOCK":
            raise HTTPException(status_code=409, detail="NEGATIVE_STOCK")
        raise
