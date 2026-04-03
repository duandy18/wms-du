# app/oms/routers/stores.py
from __future__ import annotations

from fastapi import APIRouter

from app.oms.routers import stores_bindings_read
from app.oms.routers import stores_bindings_write
from app.oms.routers import stores_crud
from app.oms.routers import stores_order_sim
from app.oms.routers import stores_routing

router = APIRouter(tags=["stores"])


def _register_all_routes() -> None:
    stores_crud.register(router)
    stores_bindings_read.register(router)
    stores_bindings_write.register(router)
    stores_routing.register(router)
    stores_order_sim.register(router)


_register_all_routes()

__all__ = ["router"]
