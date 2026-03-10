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
# 主线资源：单方案直挂的三阶段资源接口
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
#     ├ ranges
#     ├ destination_groups
#     ├ pricing_matrix_cells
#     └ surcharges
#
# 系统主写接口：
#
#   /pricing-schemes/{scheme_id}/ranges
#   /pricing-schemes/{scheme_id}/groups
#   /pricing-schemes/{scheme_id}/matrix-cells
#
# 已移除旧 modules/{module_code} 双模块主线。
