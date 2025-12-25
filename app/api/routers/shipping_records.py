# app/api/routers/shipping_records.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import shipping_records_routes_read
from app.api.routers import shipping_records_routes_status

router = APIRouter(tags=["shipping-records"])


def _register_all_routes() -> None:
    shipping_records_routes_read.register(router)
    shipping_records_routes_status.register(router)


_register_all_routes()
