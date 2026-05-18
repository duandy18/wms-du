# app/wms/system/write_v1/services/service_permission_write_service.py
from __future__ import annotations

from sqlalchemy.orm import Session

from app.wms.system.service_auth.models import (
    WmsServiceCapability,
    WmsServiceClient,
    WmsServicePermission,
)
from app.wms.system.write_v1.contracts import (
    WmsSystemServicePermissionApplyIn,
    WmsSystemServicePermissionApplyOut,
    WmsSystemServicePermissionVerifyOut,
)
from app.wms.system.write_v1.repos import WmsServicePermissionWriteRepo

WMS_APP_CODE = "wms"


class WmsServicePermissionCapabilityNotFoundError(ValueError):
    pass


class WmsServicePermissionClientCodeReservedError(ValueError):
    pass


def _strip(value: str | None) -> str:
    return (value or "").strip()


def _optional_strip(value: str | None) -> str | None:
    text = _strip(value)
    return text or None


def _is_verified(
    *,
    client: WmsServiceClient | None,
    capability: WmsServiceCapability | None,
    permission: WmsServicePermission | None,
) -> bool:
    return bool(
        client
        and capability
        and permission
        and client.is_active
        and capability.is_active
        and permission.is_active
    )


class WmsServicePermissionWriteService:
    """
    Apply and verify WMS local service permissions for ERP.

    Boundary:
    - ERP calls this service through /system/write/v1.
    - WMS remains the runtime permission source of truth.
    - This service writes only WMS local service auth execution tables.
    - This service never writes ERP and never reads user permission tables.
    """

    def __init__(
        self,
        db: Session,
        repo: WmsServicePermissionWriteRepo | None = None,
    ) -> None:
        self.repo = repo or WmsServicePermissionWriteRepo(db)

    def apply_permission(
        self,
        payload: WmsSystemServicePermissionApplyIn,
    ) -> WmsSystemServicePermissionApplyOut:
        client_code = _strip(payload.client_code)
        client_name = _strip(payload.client_name)
        capability_code = _strip(payload.capability_code)
        description = _optional_strip(payload.description)

        if client_code == "erp-service":
            raise WmsServicePermissionClientCodeReservedError(
                "erp_service_cannot_be_managed_as_target_client"
            )

        capability = self.repo.get_capability_by_code(capability_code)
        if capability is None:
            raise WmsServicePermissionCapabilityNotFoundError(
                "wms_service_capability_not_found"
            )

        client = self.repo.get_client_by_code(client_code)
        if client is None:
            client = WmsServiceClient(
                client_code=client_code,
                client_name=client_name,
                description="ERP managed service client",
                is_active=True,
            )
            self.repo.add(client)
            self.repo.flush()
        else:
            client.client_name = client_name
            client.is_active = True
            self.repo.flush()

        permission = self.repo.get_permission(
            client_id=int(client.id),
            capability_code=capability_code,
        )
        if permission is None:
            permission = WmsServicePermission(
                client_id=int(client.id),
                capability_code=capability_code,
                description=description,
                is_active=payload.is_active,
            )
            self.repo.add(permission)
        else:
            permission.description = description
            permission.is_active = payload.is_active

        self.repo.flush()
        self.repo.commit()
        self.repo.refresh(client)
        self.repo.refresh(permission)

        return WmsSystemServicePermissionApplyOut(
            app_code=WMS_APP_CODE,
            client_code=str(client.client_code),
            client_name=str(client.client_name),
            capability_code=str(permission.capability_code),
            description=permission.description,
            is_active=bool(permission.is_active),
            applied=True,
            verified=_is_verified(
                client=client,
                capability=capability,
                permission=permission,
            ),
            permission_id=int(permission.id),
            granted_at=permission.granted_at,
        )

    def verify_permission(
        self,
        *,
        client_code: str,
        capability_code: str,
    ) -> WmsSystemServicePermissionVerifyOut:
        normalized_client_code = _strip(client_code)
        normalized_capability_code = _strip(capability_code)

        client = self.repo.get_client_by_code(normalized_client_code)
        capability = self.repo.get_capability_by_code(normalized_capability_code)
        permission = None

        if client is not None:
            permission = self.repo.get_permission(
                client_id=int(client.id),
                capability_code=normalized_capability_code,
            )

        return WmsSystemServicePermissionVerifyOut(
            app_code=WMS_APP_CODE,
            client_code=normalized_client_code,
            capability_code=normalized_capability_code,
            client_exists=client is not None,
            capability_exists=capability is not None,
            permission_exists=permission is not None,
            client_is_active=bool(client.is_active) if client is not None else None,
            capability_is_active=bool(capability.is_active) if capability is not None else None,
            permission_is_active=bool(permission.is_active) if permission is not None else None,
            description=permission.description if permission is not None else None,
            verified=_is_verified(
                client=client,
                capability=capability,
                permission=permission,
            ),
            permission_id=int(permission.id) if permission is not None else None,
            granted_at=permission.granted_at if permission is not None else None,
        )


__all__ = [
    "WMS_APP_CODE",
    "WmsServicePermissionCapabilityNotFoundError",
    "WmsServicePermissionClientCodeReservedError",
    "WmsServicePermissionWriteService",
]
