# app/api/routers/outbound_ship.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import outbound_ship_routes_prepare

router = APIRouter(tags=["ship"])


def _register_all_routes() -> None:
    # 当前仅保留出库准备入口。
    #
    # 说明：
    # - /ship/calc 已转入 TMS / Quote 路由壳
    # - /ship/confirm 已废弃并删除；Shipment 主写入口统一为 orders_v2 ship-with-waybill
    # - 本文件现在只承载 prepare-from-order 这类 outbound / fulfillment preparation 语义
    outbound_ship_routes_prepare.register(router)


_register_all_routes()
