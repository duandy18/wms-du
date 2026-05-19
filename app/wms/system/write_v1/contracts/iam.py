# app/wms/system/write_v1/contracts/iam.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSystemIamUserIn(_Base):
    username: str = Field(..., min_length=1, max_length=64)
    full_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class WmsSystemIamUserPermissionIn(_Base):
    username: str = Field(..., min_length=1, max_length=64)
    permission_code: str = Field(..., min_length=1, max_length=128)
    is_active: bool = True


class WmsSystemIamApplyIn(_Base):
    users: list[WmsSystemIamUserIn] = Field(default_factory=list)
    user_permissions: list[WmsSystemIamUserPermissionIn] = Field(default_factory=list)


class WmsSystemIamPermissionDiffOut(_Base):
    username: str
    permission_code: str


class WmsSystemIamUserDiffOut(_Base):
    username: str
    field_name: str
    expected: str | bool | None
    actual: str | bool | None


class WmsSystemIamVerifyOut(_Base):
    app_code: Literal["wms"]
    verified: bool
    user_count: int
    desired_permission_count: int
    missing_users: list[str] = Field(default_factory=list)
    missing_permission_codes: list[str] = Field(default_factory=list)
    mismatched_users: list[WmsSystemIamUserDiffOut] = Field(default_factory=list)
    missing_user_permissions: list[WmsSystemIamPermissionDiffOut] = Field(default_factory=list)
    extra_user_permissions: list[WmsSystemIamPermissionDiffOut] = Field(default_factory=list)


class WmsSystemIamApplyOut(WmsSystemIamVerifyOut):
    applied: bool


__all__ = [
    "WmsSystemIamApplyIn",
    "WmsSystemIamApplyOut",
    "WmsSystemIamPermissionDiffOut",
    "WmsSystemIamUserDiffOut",
    "WmsSystemIamUserIn",
    "WmsSystemIamUserPermissionIn",
    "WmsSystemIamVerifyOut",
]
