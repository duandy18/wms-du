# app/shipping_assist/shipment/routes_prepare.py
# 分拆说明：
# - 本文件已从“大而全 prepare 路由文件”收口为薄壳聚合入口。
# - 当前只负责聚合注册：
#   1) 订单与地址 routes_prepare_orders
#   2) 包裹基础事实 routes_prepare_packages
#   3) 包裹报价 routes_prepare_quotes
# - 维护约束：
#   - 不在本文件继续堆业务路由实现
#   - 新增 prepare 路由时优先落到对应功能子文件
from __future__ import annotations

from fastapi import APIRouter

from .routes_prepare_orders import register as register_prepare_orders_routes
from .routes_prepare_packages import register as register_prepare_packages_routes
from .routes_prepare_quotes import register as register_prepare_quotes_routes


def register(router: APIRouter) -> None:
    register_prepare_orders_routes(router)
    register_prepare_packages_routes(router)
    register_prepare_quotes_routes(router)
