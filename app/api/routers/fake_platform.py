# app/api/routers/fake_platform.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import fake_platform_routes
from app.api.routers.fake_platform_helpers import build_order_ref
from app.api.routers.fake_platform_schemas import (
    FakeOrderStatusIn,
    FakeOrderStatusOut,
    PlatformEventListOut,
    PlatformEventRow,
    PlatformStr,
)

router = APIRouter(prefix="/fake-platform", tags=["fake-platform"])


def _register_all_routes() -> None:
    fake_platform_routes.register(router)


_register_all_routes()

__all__ = [
    "router",
    "PlatformStr",
    "build_order_ref",
    "FakeOrderStatusIn",
    "FakeOrderStatusOut",
    "PlatformEventRow",
    "PlatformEventListOut",
]
