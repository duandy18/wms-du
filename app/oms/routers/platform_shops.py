# app/oms/routers/platform_shops.py
from __future__ import annotations

from fastapi import APIRouter

from app.oms.routers import platform_shops_oauth
from app.oms.routers import platform_shops_tokens


router = APIRouter()


def _register_all_routes() -> None:
    platform_shops_tokens.register(router)
    platform_shops_oauth.register(router)


_register_all_routes()
