# app/api/routers/warehouses_routes.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import warehouses_routes_read
from app.api.routers import warehouses_routes_write


def register(router: APIRouter) -> None:
    warehouses_routes_read.register(router)
    warehouses_routes_write.register(router)
