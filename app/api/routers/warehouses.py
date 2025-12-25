# app/api/routers/warehouses.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import warehouses_routes
from app.api.routers.warehouses_helpers import (
    check_perm as _check_perm,
    row_to_warehouse as _row_to_warehouse,
)
from app.api.routers.warehouses_schemas import (
    WarehouseCreateIn,
    WarehouseCreateOut,
    WarehouseDetailOut,
    WarehouseListOut,
    WarehouseOut,
    WarehouseUpdateIn,
    WarehouseUpdateOut,
)

router = APIRouter(tags=["warehouses"])


def _register_all_routes() -> None:
    warehouses_routes.register(router)


_register_all_routes()

__all__ = [
    "router",
    "WarehouseOut",
    "WarehouseListOut",
    "WarehouseDetailOut",
    "WarehouseCreateIn",
    "WarehouseCreateOut",
    "WarehouseUpdateIn",
    "WarehouseUpdateOut",
    "_check_perm",
    "_row_to_warehouse",
]
