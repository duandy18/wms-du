# app/api/routers/platform_shops.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import platform_shops_routes_oauth
from app.api.routers import platform_shops_routes_tokens

router = APIRouter()


def _register_all_routes() -> None:
    platform_shops_routes_tokens.register(router)
    platform_shops_routes_oauth.register(router)


_register_all_routes()
