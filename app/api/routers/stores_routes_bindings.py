# app/api/routers/stores_routes_bindings.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import stores_routes_bindings_read
from app.api.routers import stores_routes_bindings_write


def register(router: APIRouter) -> None:
    stores_routes_bindings_read.register(router)
    stores_routes_bindings_write.register(router)
