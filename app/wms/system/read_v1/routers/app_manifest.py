# app/wms/system/read_v1/routers/app_manifest.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.system.read_v1.contracts import WmsSystemAppManifestOut
from app.wms.system.read_v1.services import build_wms_app_manifest

router = APIRouter(prefix="/system/read/v1", tags=["system-read-v1"])


@router.get(
    "/app-manifest",
    response_model=WmsSystemAppManifestOut,
    summary="Get WMS app manifest",
)
async def get_wms_app_manifest() -> WmsSystemAppManifestOut:
    """
    Return WMS self-description defaults for ERP app registration sync.

    Boundary:
    - This endpoint does not register itself into ERP.
    - This endpoint does not decide whether WMS is enabled, visible, or published in ERP.
    - This endpoint exposes no secrets and does not read/write business data.
    """

    return build_wms_app_manifest()


__all__ = ["router"]
