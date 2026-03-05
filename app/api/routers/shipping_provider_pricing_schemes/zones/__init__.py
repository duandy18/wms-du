# app/api/routers/shipping_provider_pricing_schemes/zones/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from .archive_release import register_archive_release_routes
from .create import register_create_routes
from .delete import register_delete_routes
from .province_members import register_province_members_routes
from .update import register_update_routes


def register_zones_subroutes(router: APIRouter) -> None:
    register_create_routes(router)
    register_update_routes(router)
    register_province_members_routes(router)
    register_archive_release_routes(router)
    register_delete_routes(router)
