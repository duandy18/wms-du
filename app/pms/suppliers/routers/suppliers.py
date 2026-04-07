# app/pms/suppliers/routers/suppliers.py
from __future__ import annotations

from fastapi import APIRouter

from app.pms.suppliers.routers import suppliers_routes

router = APIRouter(tags=["suppliers"])


def _register_all_routes() -> None:
    suppliers_routes.register(router)


_register_all_routes()

__all__ = ["router"]
