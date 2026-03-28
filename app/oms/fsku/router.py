# app/oms/fsku/router.py
from __future__ import annotations

from fastapi import APIRouter

from .router_fskus import register as register_fskus
from .router_store_fskus import register as register_store_fskus
from .router_merchant_code_bindings import router as merchant_code_bindings_router

router = APIRouter(tags=["oms-fsku"])

register_fskus(router)
register_store_fskus(router)
router.include_router(merchant_code_bindings_router)

__all__ = ["router"]
