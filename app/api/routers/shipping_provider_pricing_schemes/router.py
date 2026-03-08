# app/api/routers/shipping_provider_pricing_schemes/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shipping_provider_pricing_schemes_routes_module_groups import (
    register_module_groups_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_module_matrix_cells import (
    register_module_matrix_cells_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_module_ranges import (
    register_module_ranges_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme import (
    register_scheme_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_surcharges import (
    register_surcharges_routes,
)

router = APIRouter(tags=["shipping-provider-pricing"])

# -------------------------------------------------------------
# 主线：Scheme
# -------------------------------------------------------------
register_scheme_routes(router)

# -------------------------------------------------------------
# 新主线：三阶段资源接口
# -------------------------------------------------------------
register_module_ranges_routes(router)
register_module_groups_routes(router)
register_module_matrix_cells_routes(router)

# -------------------------------------------------------------
# surcharge
# -------------------------------------------------------------
register_surcharges_routes(router)

# -------------------------------------------------------------
# 说明
# -------------------------------------------------------------
#
# Level-3 pricing 当前正式写入模型：
#
#   scheme
#     └ modules
#         ├ module_ranges
#         ├ destination_groups
#         └ pricing_matrix_cells
#
# 系统主写接口：
#
#   /pricing-schemes/{scheme_id}/modules/{module_code}/ranges
#   /pricing-schemes/{scheme_id}/modules/{module_code}/groups
#   /pricing-schemes/{scheme_id}/modules/{module_code}/matrix-cells
#
# 已移除旧整表 matrix editor 主线。
