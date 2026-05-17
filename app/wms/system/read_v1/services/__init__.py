# app/wms/system/read_v1/services/__init__.py
from __future__ import annotations

from app.wms.system.read_v1.services.app_manifest_service import (
    WMS_APP_VERSION,
    build_wms_app_manifest,
)

__all__ = [
    "WMS_APP_VERSION",
    "build_wms_app_manifest",
]
