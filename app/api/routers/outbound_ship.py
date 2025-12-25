# app/api/routers/outbound_ship.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import outbound_ship_routes_calc
from app.api.routers import outbound_ship_routes_confirm
from app.api.routers import outbound_ship_routes_prepare

router = APIRouter(tags=["ship"])


def _register_all_routes() -> None:
    outbound_ship_routes_calc.register(router)
    outbound_ship_routes_prepare.register(router)
    outbound_ship_routes_confirm.register(router)


_register_all_routes()
