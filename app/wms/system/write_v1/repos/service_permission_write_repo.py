# app/wms/system/write_v1/repos/service_permission_write_repo.py
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.wms.system.service_auth.models import (
    WmsServiceCapability,
    WmsServiceClient,
    WmsServicePermission,
)


class WmsServicePermissionWriteSaveError(RuntimeError):
    pass


class WmsServicePermissionWriteRepo:
    """
    WMS service permission write repository.

    Boundary:
    - Only reads/writes wms_service_clients and wms_service_permissions.
    - Reads wms_service_capabilities only to validate target capability existence.
    - Never reads users / permissions / user_permissions.
    - Never writes ERP tables or other systems.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_client_by_code(self, client_code: str) -> WmsServiceClient | None:
        return (
            self.db.query(WmsServiceClient)
            .filter(WmsServiceClient.client_code == client_code)
            .one_or_none()
        )

    def get_capability_by_code(self, capability_code: str) -> WmsServiceCapability | None:
        return (
            self.db.query(WmsServiceCapability)
            .filter(WmsServiceCapability.capability_code == capability_code)
            .one_or_none()
        )

    def get_permission(
        self,
        *,
        client_id: int,
        capability_code: str,
    ) -> WmsServicePermission | None:
        return (
            self.db.query(WmsServicePermission)
            .filter(WmsServicePermission.client_id == client_id)
            .filter(WmsServicePermission.capability_code == capability_code)
            .one_or_none()
        )

    def add(self, row: object) -> None:
        self.db.add(row)

    def flush(self) -> None:
        try:
            self.db.flush()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise WmsServicePermissionWriteSaveError("wms_service_permission_write_flush_failed") from exc

    def commit(self) -> None:
        try:
            self.db.commit()
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise WmsServicePermissionWriteSaveError("wms_service_permission_write_commit_failed") from exc

    def refresh(self, row: object) -> None:
        self.db.refresh(row)


__all__ = [
    "WmsServicePermissionWriteRepo",
    "WmsServicePermissionWriteSaveError",
]
