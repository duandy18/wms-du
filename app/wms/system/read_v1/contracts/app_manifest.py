# app/wms/system/read_v1/contracts/app_manifest.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSystemAppManifestBuildInfoOut(_Base):
    environment: str = Field(..., min_length=1)
    git_sha: str | None = None
    build_time: str | None = None


class WmsSystemAppManifestOut(_Base):
    app_code: Literal["wms"]
    app_name: str = Field(..., min_length=1)
    app_type: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)

    default_web_path: str = Field(..., min_length=1)
    default_api_path: str = Field(..., min_length=1)
    local_web_url: str = Field(..., min_length=1)
    local_api_url: str = Field(..., min_length=1)

    health_url: str = Field(..., min_length=1)
    db_health_url: str | None = None
    openapi_url: str = Field(..., min_length=1)
    page_catalog_url: str = Field(..., min_length=1)
    service_capabilities_url: str = Field(..., min_length=1)
    service_dependencies_url: str = Field(..., min_length=1)

    version: str = Field(..., min_length=1)
    build_info: WmsSystemAppManifestBuildInfoOut


__all__ = [
    "WmsSystemAppManifestBuildInfoOut",
    "WmsSystemAppManifestOut",
]
