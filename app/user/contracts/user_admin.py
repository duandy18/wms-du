# app/user/contracts/user_admin.py
from __future__ import annotations

from pydantic import BaseModel, Field


class UserCreateMulti(BaseModel):
    username: str
    password: str
    permission_ids: list[int] = Field(default_factory=list)
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None


class UserUpdateMulti(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool | None = None


class UserSetPermissionsIn(BaseModel):
    permission_ids: list[int] = Field(default_factory=list)


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


class PasswordResetIn(BaseModel):
    pass


__all__ = [
    "UserCreateMulti",
    "UserUpdateMulti",
    "UserSetPermissionsIn",
    "PasswordChangeIn",
    "PasswordResetIn",
]
