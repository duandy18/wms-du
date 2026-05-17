# app/wms/system/read_v1/routers/service_dependencies.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.system.read_v1.contracts import WmsSystemServiceDependenciesOut
from app.wms.system.read_v1.services import build_wms_service_dependencies

router = APIRouter(prefix="/system/read/v1", tags=["system-read-v1"])


@router.get(
    "/service-dependencies",
    response_model=WmsSystemServiceDependenciesOut,
    summary="Get WMS service dependencies",
)
async def get_wms_service_dependencies() -> WmsSystemServiceDependenciesOut:
    """
    Return WMS declared outbound service dependencies for ERP collaboration sync.

    Boundary:
    - Declared dependency does not mean approved.
    - Declared dependency does not mean permission has been written to target system.
    - Declared dependency does not mean runtime verification has passed.
    - ERP remains responsible for matching, approval, write-back, and verification state.
    """

    return build_wms_service_dependencies()


__all__ = ["router"]
