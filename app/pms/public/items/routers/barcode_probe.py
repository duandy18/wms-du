# app/pms/public/items/routers/barcode_probe.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.pms.public.items.contracts.barcode_probe import BarcodeProbeIn, BarcodeProbeOut
from app.pms.public.items.services.barcode_probe_service import BarcodeProbeService

router = APIRouter(tags=["pms-public-items"])


def get_barcode_probe_service(db: Session = Depends(get_db)) -> BarcodeProbeService:
    return BarcodeProbeService(db)


@router.post("/items/barcode-probe", response_model=BarcodeProbeOut)
def probe_barcode(
    body: BarcodeProbeIn,
    service: BarcodeProbeService = Depends(get_barcode_probe_service),
) -> BarcodeProbeOut:
    return service.probe(barcode=body.barcode)
