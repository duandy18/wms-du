# app/api/routers/user.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import user_routes_admin
from app.api.routers import user_routes_auth
from app.api.routers import user_routes_me
from app.api.routers import user_routes_password
from app.api.routers.user_schemas import (
    PasswordChangeIn,
    PasswordResetIn,
    UserCreateMulti,
    UserUpdateMulti,
)

router = APIRouter(prefix="/users", tags=["users"])


def _register_all_routes() -> None:
    user_routes_auth.register(router)
    user_routes_admin.register(router)
    user_routes_me.register(router)
    user_routes_password.register(router)


_register_all_routes()

__all__ = [
    "router",
    "UserCreateMulti",
    "UserUpdateMulti",
    "PasswordChangeIn",
    "PasswordResetIn",
]
