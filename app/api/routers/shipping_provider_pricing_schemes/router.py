# app/api/routers/shipping_provider_pricing_schemes/router.py
from __future__ import annotations

from fastapi import APIRouter

# ===== 子路由注册函数 =====
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme import (
    register_scheme_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_scheme_warehouses import (
    register as register_scheme_warehouses_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_zones import (
    register_zones_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_members import (
    register_members_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_brackets import (
    register_brackets_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_surcharges import (
    register_surcharges_routes,
)
from app.api.routers.shipping_provider_pricing_schemes_routes_segment_templates import (
    register_segment_templates_routes,
)
from app.api.routers.shipping_provider_pricing_schemes.dest_adjustments.routes import (
    register_dest_adjustments_routes,
)

# ==========================
# Router 聚合（唯一出口）
# ==========================
router = APIRouter(tags=["shipping-provider-pricing"])

# 注意：顺序是**业务阅读顺序**，不是技术顺序
register_scheme_routes(router)  # pricing-schemes CRUD
register_scheme_warehouses_routes(router)  # ✅ Phase 3: scheme origin warehouses
register_segment_templates_routes(router)  # ✅ segments templates (draft/publish/activate)
register_zones_routes(router)  # zones / zones-atomic
register_members_routes(router)  # zone members
register_brackets_routes(router)  # brackets + copy
register_surcharges_routes(router)  # surcharges
register_dest_adjustments_routes(router)  # ✅ dest adjustments (structured destination facts)
