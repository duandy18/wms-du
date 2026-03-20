from __future__ import annotations

from fastapi import APIRouter

from .endpoints.clone import register_clone_routes
from .endpoints.create import register_create_routes
from .endpoints.publish import register_publish_routes
from .endpoints.update import register_update_routes


def register(router: APIRouter) -> None:
    register_create_routes(router)
    register_update_routes(router)
    register_clone_routes(router)
    register_publish_routes(router)
