# app/api/routers/shipping_provider_pricing_schemes/scheme_read/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from .debug_routes import register_debug_routes
from .detail_routes import register_detail_routes
from .list_routes import register_list_routes
from .matrix_routes import register_matrix_routes


def register_scheme_read_routes(router: APIRouter) -> None:
    """
    Scheme Read 路由聚合（按功能分拆）：
    - list_routes：列表（含 active 快捷入口）
    - detail_routes：详情
    - matrix_routes：二维 matrix
    - debug_routes：debug echo
    """
    register_list_routes(router)
    register_detail_routes(router)
    register_matrix_routes(router)
    register_debug_routes(router)
