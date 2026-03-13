# app/tms/reports/router.py
#
# 分拆说明：
# - 本文件是 TMS / Reports 的路由壳。
# - 目标是把 shipping_reports 相关入口从历史 app/api/routers 外壳中收口到 TMS 语义下。
# - 当前不改 URL，只调整物理归属。
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import shipping_reports_routes_aggregates
from app.api.routers import shipping_reports_routes_list
from app.api.routers import shipping_reports_routes_options

router = APIRouter(tags=["shipping-reports"])


def _register_all_routes() -> None:
    shipping_reports_routes_aggregates.register(router)
    shipping_reports_routes_list.register(router)
    shipping_reports_routes_options.register(router)


_register_all_routes()
