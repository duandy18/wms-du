# app/wms/system/write_v1/contracts/service_permissions.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSystemServicePermissionApplyIn(_Base):
    client_code: str = Field(..., min_length=1, max_length=64)
    client_name: str = Field(..., min_length=1, max_length=128)
    capability_code: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=255)
    is_active: bool


class WmsSystemServicePermissionApplyOut(_Base):
    app_code: Literal["wms"]
    client_code: str
    client_name: str
    capability_code: str
    description: str | None
    is_active: bool
    applied: bool
    verified: bool
    permission_id: int
    granted_at: datetime


class WmsSystemServicePermissionVerifyOut(_Base):
    app_code: Literal["wms"]
    client_code: str
    capability_code: str
    client_exists: bool
    capability_exists: bool
    permission_exists: bool
    client_is_active: bool | None
    capability_is_active: bool | None
    permission_is_active: bool | None
    description: str | None
    verified: bool
    permission_id: int | None
    granted_at: datetime | None


__all__ = [
    "WmsSystemServicePermissionApplyIn",
    "WmsSystemServicePermissionApplyOut",
    "WmsSystemServicePermissionVerifyOut",
]
