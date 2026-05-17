# app/wms/system/read_v1/routers/service_capabilities.py
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.wms.system.read_v1.contracts import WmsSystemServiceCapabilitiesOut
from app.wms.system.read_v1.repos import WmsServiceCapabilityReadRepo
from app.wms.system.read_v1.services import WmsServiceCapabilityReadService

router = APIRouter(prefix="/system/read/v1", tags=["system-read-v1"])


@router.get(
    "/service-capabilities",
    response_model=WmsSystemServiceCapabilitiesOut,
    summary="Get WMS service capabilities",
)
async def get_wms_service_capabilities(
    db: Session = Depends(get_db),
) -> WmsSystemServiceCapabilitiesOut:
    """
    Return WMS service capabilities for ERP system collaboration sync.

    Boundary:
    - WMS declares what WMS provides.
    - ERP must not guess WMS capabilities.
    - This endpoint is read-only.
    - This endpoint does not expose approval, grant, written, or verified state.
    """

    return WmsServiceCapabilityReadService(
        WmsServiceCapabilityReadRepo(db),
    ).get_service_capabilities()


__all__ = ["router"]
