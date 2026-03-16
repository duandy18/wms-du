# app/tms/config/warehouse_provider_bindings/router.py
# 分拆说明：
# - 本文件是 TransportConfig / warehouse_provider_bindings 子域路由壳；
# - 统一装配仓库-运输网点绑定关系接口与 active carriers summary；
# - URL 继续保留 /warehouses/... 口径，但物理归属已收口到 TMS / config。
from __future__ import annotations

from fastapi import APIRouter

from . import routes_bindings, routes_summary

router = APIRouter()


def _register_all_routes() -> None:
    routes_summary.register(router)
    routes_bindings.register(router)


_register_all_routes()
