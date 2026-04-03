# app/wms/warehouses/routers/warehouses.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.warehouses.routers import warehouses_routes

router = APIRouter(tags=["warehouses"])


def _register_all_routes() -> None:
    warehouses_routes.register(router)


_register_all_routes()

__all__ = ["router"]
