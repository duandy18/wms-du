# app/api/routers/shipping_provider_pricing_schemes_routes_brackets.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shipping_provider_pricing_schemes_routes_brackets_crud import (
    register_brackets_crud_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_brackets_copy import (
    register_brackets_copy_routes,
)


def register_brackets_routes(router: APIRouter) -> None:
    # CRUD: create/update/delete
    register_brackets_crud_routes(router)

    # Copy: brackets:copy
    register_brackets_copy_routes(router)
