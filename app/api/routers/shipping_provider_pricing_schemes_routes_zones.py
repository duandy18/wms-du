# app/api/routers/shipping_provider_pricing_schemes_routes_zones.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shipping_provider_pricing_schemes.zones import register_zones_subroutes


def register_zones_routes(router: APIRouter) -> None:
    register_zones_subroutes(router)
