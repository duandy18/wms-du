# app/tms/shipment/router.py
#
# 分拆说明：
# - 本文件承载 TMS / Shipment 在 /ship 下的查询/准备类入口。
# - /ship/calc 与 /ship/prepare-from-order 属于 Shipment 应用层入口：
#   内部可调用 Quote 能力，但物理归属属于 Shipment。
# - /ship-with-waybill 不在此路由壳，仍走 orders_v2_router。
from __future__ import annotations

from fastapi import APIRouter

from .routes_calc import register as register_calc_routes
from .routes_prepare import register as register_prepare_routes
from .routes_waybill_config import register as register_waybill_config_routes

router = APIRouter(tags=["ship"])


register_calc_routes(router)
register_prepare_routes(router)
register_waybill_config_routes(router)
