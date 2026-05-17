# app/wms/system/read_v1/contracts/service_capabilities.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSystemServiceCapabilityRouteOut(_Base):
    http_method: str = Field(..., min_length=1, max_length=16)
    path: str = Field(..., min_length=1, max_length=255)
    route_name: str = Field(..., min_length=1, max_length=128)
    auth_required: bool
    is_active: bool
    source_created_at: datetime | None = None


class WmsSystemServiceCapabilityOut(_Base):
    capability_code: str = Field(..., min_length=1, max_length=128)
    capability_name: str = Field(..., min_length=1, max_length=128)
    resource_code: str = Field(..., min_length=1, max_length=64)
    permission_code: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool
    source_updated_at: datetime | None = None
    routes: list[WmsSystemServiceCapabilityRouteOut] = Field(default_factory=list)


class WmsSystemServiceCapabilitiesOut(_Base):
    app_code: Literal["wms"]
    app_name: str = Field(..., min_length=1)
    capabilities: list[WmsSystemServiceCapabilityOut] = Field(default_factory=list)


__all__ = [
    "WmsSystemServiceCapabilitiesOut",
    "WmsSystemServiceCapabilityOut",
    "WmsSystemServiceCapabilityRouteOut",
]
