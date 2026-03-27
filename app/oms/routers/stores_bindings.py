# app/oms/routers/stores_bindings.py
from __future__ import annotations

from fastapi import APIRouter

from app.oms.routers import stores_bindings_read
from app.oms.routers import stores_bindings_write


def register(router: APIRouter) -> None:
    stores_bindings_read.register(router)
    stores_bindings_write.register(router)
