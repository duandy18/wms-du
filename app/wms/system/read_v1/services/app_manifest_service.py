# app/wms/system/read_v1/services/app_manifest_service.py
from __future__ import annotations

import os

from app.wms.system.read_v1.contracts import (
    WmsSystemAppManifestBuildInfoOut,
    WmsSystemAppManifestOut,
)

WMS_APP_VERSION = "1.1.0"


def _env_value(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def build_wms_app_manifest() -> WmsSystemAppManifestOut:
    version = _env_value("WMS_APP_VERSION", "APP_VERSION") or WMS_APP_VERSION

    return WmsSystemAppManifestOut(
        app_code="wms",
        app_name="仓储管理",
        app_type="business_system",
        status="available",
        description="WMS 仓储管理系统，负责库存、入库、出库、仓库与仓内作业等仓储域能力。",
        default_web_path="/wms/",
        default_api_path="/api/wms",
        local_web_url=_env_value("WMS_LOCAL_WEB_URL") or "http://127.0.0.1:5173",
        local_api_url=_env_value("WMS_LOCAL_API_URL") or "http://127.0.0.1:8000",
        health_url="/healthz",
        db_health_url=_env_value("WMS_DB_HEALTH_URL"),
        openapi_url="/openapi.json",
        page_catalog_url="/system/read/v1/page-catalog",
        service_capabilities_url="/system/read/v1/service-capabilities",
        service_dependencies_url="/system/read/v1/service-dependencies",
        version=version,
        build_info=WmsSystemAppManifestBuildInfoOut(
            environment=_env_value("WMS_ENV", "ENV") or "dev",
            git_sha=_env_value("WMS_GIT_SHA", "GIT_SHA", "COMMIT_SHA"),
            build_time=_env_value("WMS_BUILD_TIME", "BUILD_TIME"),
        ),
    )


__all__ = [
    "WMS_APP_VERSION",
    "build_wms_app_manifest",
]
