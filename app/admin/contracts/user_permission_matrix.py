# app/admin/contracts/user_permission_matrix.py
from __future__ import annotations

from pydantic import BaseModel, Field


class PagePermissionCellOut(BaseModel):
    read: bool = False
    write: bool = False


class PermissionMatrixPageOut(BaseModel):
    page_code: str
    page_name: str
    sort_order: int = 0


class PermissionMatrixRowOut(BaseModel):
    user_id: int
    username: str
    full_name: str | None = None
    is_active: bool
    pages: dict[str, PagePermissionCellOut] = Field(default_factory=dict)


class UserPermissionMatrixOut(BaseModel):
    pages: list[PermissionMatrixPageOut] = Field(default_factory=list)
    rows: list[PermissionMatrixRowOut] = Field(default_factory=list)


__all__ = [
    "PagePermissionCellOut",
    "PermissionMatrixPageOut",
    "PermissionMatrixRowOut",
    "UserPermissionMatrixOut",
]
