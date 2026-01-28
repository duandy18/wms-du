from __future__ import annotations

from fastapi import APIRouter

from .endpoints.create import register_create_routes
from .endpoints.default_segment_template import register_default_segment_template_routes
from .endpoints.segment_active import register_segment_active_routes
from .endpoints.update import register_update_routes


def register(router: APIRouter) -> None:
    """
    Shipping Provider Pricing Schemes - WRITE routes (split)
    Keep paths unchanged; orchestration only.
    """
    register_create_routes(router)
    register_update_routes(router)
    register_default_segment_template_routes(router)
    register_segment_active_routes(router)
