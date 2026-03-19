# app/tms/config/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.tms.config.providers.router import router as providers_router

router = APIRouter()
router.include_router(providers_router)
