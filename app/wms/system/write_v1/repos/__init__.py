# app/wms/system/write_v1/repos/__init__.py
from __future__ import annotations

from app.wms.system.write_v1.repos.service_permission_write_repo import (
    WmsServicePermissionWriteRepo,
    WmsServicePermissionWriteSaveError,
)

__all__ = [
    "WmsServicePermissionWriteRepo",
    "WmsServicePermissionWriteSaveError",
]
