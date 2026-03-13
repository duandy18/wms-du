# app/tms/shipment/orders_v2_router.py
#
# 分拆说明：
# - 本文件是 TMS / Shipment 在 orders_fulfillment_v2 下的路由壳。
# - 历史上 /orders 下的 ship / ship-with-waybill 与 reserve / pick 混挂在同一组 router 中。
# - 当前将运输执行相关入口单独收口为 TMS Shipment 语义壳，便于后续继续做物理迁移。
# - 当前不改 URL，只调整物理归属。
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import orders_fulfillment_v2_routes_3_ship
from app.api.routers import orders_fulfillment_v2_routes_4_ship_with_waybill

router = APIRouter(prefix="/orders", tags=["orders-fulfillment-v2"])


def _register_all_routes() -> None:
    orders_fulfillment_v2_routes_3_ship.register(router)
    orders_fulfillment_v2_routes_4_ship_with_waybill.register(router)


_register_all_routes()
