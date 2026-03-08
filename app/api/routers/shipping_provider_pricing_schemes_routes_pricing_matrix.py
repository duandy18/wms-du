# app/api/routers/shipping_provider_pricing_schemes_routes_pricing_matrix.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix_matrix_editor import (
    register_pricing_matrix_matrix_editor_routes,
)


def register_pricing_matrix_routes(router: APIRouter) -> None:
    """
    Pricing Matrix 路由入口（Phase-3 收口版）

    当前系统定价模型已经升级为 Level-3：

        scheme
          └── modules
                ├── ranges
                └── destination_groups
                        └── pricing_matrix (group × range)

    因此矩阵编辑的正式合同为：

        GET /pricing-schemes/{scheme_id}/matrix-view
        PUT /pricing-schemes/{scheme_id}/matrix

    旧的 group 级 pricing-matrix CRUD / replace / copy 接口
    属于历史模型（group × weight_range 直接维护 min/max），
    与当前 module_range_id 结构不一致，因此不再从系统入口注册。
    """

    register_pricing_matrix_matrix_editor_routes(router)
