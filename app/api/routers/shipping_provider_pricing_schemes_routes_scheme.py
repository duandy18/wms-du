# app/api/routers/shipping_provider_pricing_schemes_routes_scheme.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import shipping_provider_pricing_schemes_routes_scheme_read
from app.api.routers import shipping_provider_pricing_schemes_routes_scheme_write


def register_scheme_routes(router: APIRouter) -> None:
    """
    Scheme 路由聚合入口（保持对外函数名不变）。
    """
    shipping_provider_pricing_schemes_routes_scheme_read.register(router)
    shipping_provider_pricing_schemes_routes_scheme_write.register(router)
