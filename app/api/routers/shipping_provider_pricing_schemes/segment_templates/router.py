# app/api/routers/shipping_provider_pricing_schemes/segment_templates/router.py
from __future__ import annotations

from fastapi import APIRouter

from .endpoints.detail import register_detail_routes
from .endpoints.items import register_items_routes
from .endpoints.lifecycle_activate import register_activate_routes
from .endpoints.lifecycle_archive import register_archive_routes
from .endpoints.lifecycle_publish import register_publish_routes
from .endpoints.list_create import register_list_create_routes


def register_segment_templates_routes(router: APIRouter) -> None:
    """
    Segment Templates Router (split)
    - keep endpoint paths unchanged
    - orchestration only (no business here)
    """
    register_list_create_routes(router)
    register_detail_routes(router)
    register_items_routes(router)
    register_publish_routes(router)
    register_activate_routes(router)
    register_archive_routes(router)
