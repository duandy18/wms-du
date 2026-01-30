# app/api/routers/shipping_provider_pricing_schemes_routes_scheme_read.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shipping_provider_pricing_schemes.scheme_read import register_scheme_read_routes


def register(router: APIRouter) -> None:
    """
    Scheme Read Routes Facade（按功能已拆分到 scheme_read/*）：
    - list_routes：列表（含 active 快捷入口）
    - detail_routes：详情
    - matrix_routes：二维 matrix（active zone 过滤合同）
    - debug_routes：debug echo
    """
    register_scheme_read_routes(router)
