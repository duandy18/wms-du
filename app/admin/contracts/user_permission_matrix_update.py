# app/admin/contracts/user_permission_matrix_update.py
from __future__ import annotations

from pydantic import BaseModel, Field


class PagePermissionCellIn(BaseModel):
    read: bool = False
    write: bool = False


class UserPermissionMatrixUpdateIn(BaseModel):
    pages: dict[str, PagePermissionCellIn] = Field(default_factory=dict)


__all__ = [
    "PagePermissionCellIn",
    "UserPermissionMatrixUpdateIn",
]
