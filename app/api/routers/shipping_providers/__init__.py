# app/api/routers/shipping_providers/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from .providers import router as providers_router

router = APIRouter(tags=["shipping-providers"])
router.include_router(providers_router)
