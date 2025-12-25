# app/api/routers/user_schemas.py
from __future__ import annotations

from pydantic import BaseModel


class UserCreateMulti(BaseModel):
    username: str
    password: str
    primary_role_id: int
    extra_role_ids: list[int] = []
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None


class UserUpdateMulti(BaseModel):
    primary_role_id: int | None = None
    extra_role_ids: list[int] | None = None
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool | None = None


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


class PasswordResetIn(BaseModel):
    pass
