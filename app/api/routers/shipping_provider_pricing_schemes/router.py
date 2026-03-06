# app/api/routers/shipping_provider_pricing_schemes/router.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers.shipping_provider_pricing_schemes_routes_pricing_matrix import (
    register_pricing_matrix_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme import (
    register_scheme_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_surcharges import (
    register_surcharges_routes,
)

router = APIRouter(tags=["shipping-provider-pricing"])

# 顺序按业务阅读路径组织：
register_scheme_routes(router)  # pricing-schemes CRUD
register_pricing_matrix_routes(router)  # level3 pricing_matrix CRUD + copy
register_surcharges_routes(router)  # surcharge-only（含目的地附加费）

# 当前主线：
#   destination_group + pricing_matrix + surcharge
#
# 已从系统入口摘除：
# - legacy zones
# - legacy zone members
# - legacy zone brackets
