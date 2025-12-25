# app/api/routers/shipping_reports.py
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import shipping_reports_routes_aggregates
from app.api.routers import shipping_reports_routes_list
from app.api.routers import shipping_reports_routes_options

router = APIRouter(tags=["shipping-reports"])


def _register_all_routes() -> None:
    # 聚合统计类
    shipping_reports_routes_aggregates.register(router)
    # 明细列表
    shipping_reports_routes_list.register(router)
    # 下拉选项
    shipping_reports_routes_options.register(router)


_register_all_routes()
