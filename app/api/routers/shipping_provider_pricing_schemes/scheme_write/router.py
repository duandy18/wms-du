from __future__ import annotations

from fastapi import APIRouter

from .endpoints.create import register_create_routes
from .endpoints.update import register_update_routes


def register(router: APIRouter) -> None:
    """
    Shipping Provider Pricing Schemes - WRITE routes

    当前保留：
    - create
    - update
    """
    register_create_routes(router)
    register_update_routes(router)
