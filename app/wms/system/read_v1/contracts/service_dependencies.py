# app/wms/system/read_v1/contracts/service_dependencies.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSystemServiceDependencyEndpointOut(_Base):
    http_method: str = Field(..., min_length=1, max_length=16)
    path: str = Field(..., min_length=1, max_length=255)
    purpose: str | None = Field(default=None, max_length=255)


class WmsSystemServiceDependencyOut(_Base):
    dependency_code: str = Field(..., min_length=1, max_length=128)
    dependency_name: str = Field(..., min_length=1, max_length=128)

    target_app_code: str = Field(..., min_length=1, max_length=64)
    target_capability_code: str = Field(..., min_length=1, max_length=128)
    required_permission_code: str = Field(..., min_length=1, max_length=128)

    description: str | None = Field(default=None, max_length=255)
    is_required: bool
    is_active: bool

    required_config_keys: list[str] = Field(default_factory=list)
    source_modules: list[str] = Field(default_factory=list)
    endpoints: list[WmsSystemServiceDependencyEndpointOut] = Field(default_factory=list)


class WmsSystemServiceDependenciesOut(_Base):
    app_code: Literal["wms"]
    app_name: str = Field(..., min_length=1)
    source_service_client_code: Literal["wms-service"]
    dependencies: list[WmsSystemServiceDependencyOut] = Field(default_factory=list)


__all__ = [
    "WmsSystemServiceDependenciesOut",
    "WmsSystemServiceDependencyEndpointOut",
    "WmsSystemServiceDependencyOut",
]
