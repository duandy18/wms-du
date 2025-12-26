# app/api/routers/shipping_provider_pricing_schemes_routes_segment_templates.py
from __future__ import annotations

# NOTE:
# 原文件过大（~360 行），已拆分到：
# - app/api/routers/shipping_provider_pricing_schemes/segment_templates/helpers.py
# - app/api/routers/shipping_provider_pricing_schemes/segment_templates/routes.py
#
# 为了保持旧 import 路径不变，这里仅 re-export。

from app.api.routers.shipping_provider_pricing_schemes.segment_templates.routes import (  # noqa: F401
    register_segment_templates_routes,
)
