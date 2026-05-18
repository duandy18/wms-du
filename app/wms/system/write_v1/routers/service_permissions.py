# app/wms/system/write_v1/routers/service_permissions.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.wms.system.service_auth.deps import WMS_SERVICE_CLIENT_HEADER
from app.wms.system.write_v1.contracts import (
    WmsSystemServicePermissionApplyIn,
    WmsSystemServicePermissionApplyOut,
    WmsSystemServicePermissionVerifyOut,
)
from app.wms.system.write_v1.repos import WmsServicePermissionWriteSaveError
from app.wms.system.write_v1.services import (
    WmsServicePermissionCapabilityNotFoundError,
    WmsServicePermissionClientCodeReservedError,
    WmsServicePermissionWriteService,
)

router = APIRouter(prefix="/system/write/v1", tags=["system-write-v1"])

ERP_SERVICE_CLIENT_CODE = "erp-service"


def require_erp_service_client(
    x_service_client: str | None = Header(default=None, alias=WMS_SERVICE_CLIENT_HEADER),
) -> None:
    client_code = (x_service_client or "").strip()

    if not client_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="wms_service_client_required",
        )

    if client_code != ERP_SERVICE_CLIENT_CODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="wms_service_permission_write_denied",
        )


@router.post(
    "/service-permissions/apply",
    response_model=WmsSystemServicePermissionApplyOut,
    summary="Apply WMS service permission",
)
async def apply_wms_service_permission(
    payload: WmsSystemServicePermissionApplyIn,
    _erp_service_client: None = Depends(require_erp_service_client),
    db: Session = Depends(get_db),
) -> WmsSystemServicePermissionApplyOut:
    """
    Apply one WMS local service permission from ERP.

    Boundary:
    - Only X-Service-Client: erp-service may call this endpoint.
    - Writes only wms_service_clients and wms_service_permissions.
    - Does not write ERP tables.
    - Does not write other systems.
    - Does not read users / permissions / user_permissions.
    """

    try:
        return WmsServicePermissionWriteService(db).apply_permission(payload)
    except WmsServicePermissionCapabilityNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WmsServicePermissionClientCodeReservedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except WmsServicePermissionWriteSaveError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/service-permissions/verify",
    response_model=WmsSystemServicePermissionVerifyOut,
    summary="Verify WMS service permission",
)
async def verify_wms_service_permission(
    client_code: str = Query(..., min_length=1, max_length=64),
    capability_code: str = Query(..., min_length=1, max_length=128),
    _erp_service_client: None = Depends(require_erp_service_client),
    db: Session = Depends(get_db),
) -> WmsSystemServicePermissionVerifyOut:
    """
    Verify one WMS local service permission for ERP.

    Boundary:
    - Only X-Service-Client: erp-service may call this endpoint.
    - Reads only wms_service_clients, wms_service_capabilities, and wms_service_permissions.
    - Does not write anything.
    - Does not read users / permissions / user_permissions.
    """

    return WmsServicePermissionWriteService(db).verify_permission(
        client_code=client_code,
        capability_code=capability_code,
    )


__all__ = ["router"]
