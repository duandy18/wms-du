# app/wms/system/read_v1/contracts/iam_snapshot.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WmsSystemIamSnapshotUserOut(_Base):
    user_id: int = Field(..., ge=1)
    username: str = Field(..., min_length=1, max_length=64)
    is_active: bool
    full_name: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)


class WmsSystemIamSnapshotPermissionOut(_Base):
    permission_id: int = Field(..., ge=1)
    permission_code: str = Field(..., min_length=1, max_length=128)


class WmsSystemIamSnapshotUserPermissionOut(_Base):
    user_id: int = Field(..., ge=1)
    permission_id: int = Field(..., ge=1)
    permission_code: str = Field(..., min_length=1, max_length=128)
    granted_at: datetime


class WmsSystemIamSnapshotPageOut(_Base):
    page_code: str = Field(..., min_length=1, max_length=64)
    page_name: str = Field(..., min_length=1, max_length=64)
    parent_page_code: str | None = Field(default=None, max_length=64)
    level: int = Field(..., ge=1, le=3)
    domain_code: str = Field(..., min_length=1, max_length=32)
    show_in_topbar: bool
    show_in_sidebar: bool
    inherit_permissions: bool
    read_permission_code: str | None = Field(default=None, max_length=128)
    write_permission_code: str | None = Field(default=None, max_length=128)
    sort_order: int
    is_active: bool


class WmsSystemIamSnapshotRoutePrefixOut(_Base):
    id: int = Field(..., ge=1)
    page_code: str = Field(..., min_length=1, max_length=64)
    route_prefix: str = Field(..., min_length=1, max_length=255)
    sort_order: int
    is_active: bool


class WmsSystemIamSnapshotOut(_Base):
    app_code: Literal["wms"]
    app_name: str = Field(..., min_length=1)
    snapshot_at: datetime
    users: list[WmsSystemIamSnapshotUserOut] = Field(default_factory=list)
    permissions: list[WmsSystemIamSnapshotPermissionOut] = Field(default_factory=list)
    user_permissions: list[WmsSystemIamSnapshotUserPermissionOut] = Field(default_factory=list)
    page_registry: list[WmsSystemIamSnapshotPageOut] = Field(default_factory=list)
    page_route_prefixes: list[WmsSystemIamSnapshotRoutePrefixOut] = Field(default_factory=list)


__all__ = [
    "WmsSystemIamSnapshotOut",
    "WmsSystemIamSnapshotPageOut",
    "WmsSystemIamSnapshotPermissionOut",
    "WmsSystemIamSnapshotRoutePrefixOut",
    "WmsSystemIamSnapshotUserOut",
    "WmsSystemIamSnapshotUserPermissionOut",
]
