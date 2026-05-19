# app/wms/system/write_v1/routers/iam.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.wms.system.write_v1.contracts import (
    WmsSystemIamApplyIn,
    WmsSystemIamApplyOut,
    WmsSystemIamVerifyOut,
)
from app.wms.system.write_v1.repos import WmsIamWriteSaveError
from app.wms.system.write_v1.routers.service_permissions import require_erp_service_client
from app.wms.system.write_v1.services import (
    WmsIamPayloadError,
    WmsIamPermissionNotFoundError,
    WmsIamWriteService,
)

router = APIRouter(prefix="/system/write/v1", tags=["system-write-v1"])


@router.post(
    "/iam/apply",
    response_model=WmsSystemIamApplyOut,
    summary="Apply WMS IAM desired state",
)
async def apply_wms_iam(
    payload: WmsSystemIamApplyIn,
    _erp_service_client: None = Depends(require_erp_service_client),
    db: Session = Depends(get_db),
) -> WmsSystemIamApplyOut:
    """
    Apply WMS local user IAM runtime projection from ERP.

    Boundary:
    - Only X-Service-Client: erp-service may call this endpoint.
    - Writes only users / user_permissions.
    - Reads permissions only to validate WMS-owned permission codes.
    - Does not create unknown permissions.
    - Does not write page_registry / page_route_prefixes.
    """

    try:
        return WmsIamWriteService(db).apply(payload)
    except WmsIamPermissionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WmsIamPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except WmsIamWriteSaveError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post(
    "/iam/verify",
    response_model=WmsSystemIamVerifyOut,
    summary="Verify WMS IAM desired state",
)
async def verify_wms_iam(
    payload: WmsSystemIamApplyIn,
    _erp_service_client: None = Depends(require_erp_service_client),
    db: Session = Depends(get_db),
) -> WmsSystemIamVerifyOut:
    """
    Verify WMS local user IAM runtime projection against ERP desired state.
    """

    try:
        return WmsIamWriteService(db).verify(payload)
    except WmsIamPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


__all__ = ["router"]
