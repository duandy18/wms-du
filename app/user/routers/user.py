# app/user/routers/user.py
from __future__ import annotations

from fastapi import APIRouter

from app.user.routers import user_routes_auth
from app.user.routers import user_routes_me
from app.user.routers import user_routes_password

router = APIRouter(prefix="/users", tags=["users"])


def _register_all_routes() -> None:
    user_routes_auth.register(router)
    user_routes_me.register(router)
    user_routes_password.register(router)


_register_all_routes()

__all__ = ["router"]
