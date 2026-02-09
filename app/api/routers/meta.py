# app/api/routers/meta.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import meta_platforms_routes

router = APIRouter(prefix="/meta", tags=["meta"])


def _register_all_routes() -> None:
    meta_platforms_routes.register(router)


_register_all_routes()

__all__ = ["router"]
