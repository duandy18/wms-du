# app/api/routers/shipping_providers/providers.py
from __future__ import annotations

from fastapi import APIRouter

from . import providers_routes_read
from . import providers_routes_write

router = APIRouter()


def _register_all_routes() -> None:
    providers_routes_read.register(router)
    providers_routes_write.register(router)


_register_all_routes()
