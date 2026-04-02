# app/wms/suppliers/routers/suppliers.py
from __future__ import annotations

from fastapi import APIRouter

from app.wms.suppliers.routers import suppliers_routes
from app.wms.suppliers.routers.suppliers_helpers import (
    check_perm as _check_perm,
    contacts_out as _contacts_out,
)
from app.wms.suppliers.routers.suppliers_schemas import (
    SupplierContactOut,
    SupplierCreateIn,
    SupplierOut,
    SupplierUpdateIn,
)

router = APIRouter(tags=["suppliers"])


def _register_all_routes() -> None:
    suppliers_routes.register(router)


_register_all_routes()

__all__ = [
    "router",
    "SupplierContactOut",
    "SupplierOut",
    "SupplierCreateIn",
    "SupplierUpdateIn",
    "_check_perm",
    "_contacts_out",
]
