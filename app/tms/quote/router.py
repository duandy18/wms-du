# app/tms/quote/router.py
#
# 分拆说明：
# - 本文件是 TMS / Quote 的路由壳。
# - 目标是把运输报价相关入口从历史 app/api/routers 外壳中收口到 TMS 语义下。
# - 当前仍复用原有 route register 实现，不改 URL，只调整物理归属。
# - 特别说明：/ship/calc 历史上挂在 outbound_ship 下，但语义属于 Quote，因此也在此处统一挂载。
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import outbound_ship_routes_calc
from app.api.routers import shipping_quote_routes_calc
from app.api.routers import shipping_quote_routes_recommend

router = APIRouter(tags=["shipping-quote"])


def _register_all_routes() -> None:
    shipping_quote_routes_calc.register(router)
    shipping_quote_routes_recommend.register(router)
    outbound_ship_routes_calc.register(router)


_register_all_routes()
