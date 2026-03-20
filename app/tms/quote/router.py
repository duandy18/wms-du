from __future__ import annotations

from fastapi import APIRouter

from .routes_calc import register as register_calc_routes
from .routes_recommend import register as register_recommend_routes

router = APIRouter(tags=["tms-quote"])

register_calc_routes(router)
register_recommend_routes(router)
