# app/tms/reports/router.py
#
# 分拆说明：
# - 本文件是 TMS / Reports 的路由装配入口。
# - Reports 域只保留聚合分析与筛选项；
# - 物流台帐明细列表已收口到 app/tms/records/；
# - 不再注册明细 list 路由。
from __future__ import annotations

from fastapi import APIRouter

from app.tms.reports import routes_aggregates
from app.tms.reports import routes_options

router = APIRouter(tags=["shipping-assist-reports"])


def _register_all_routes() -> None:
    routes_aggregates.register(router)
    routes_options.register(router)


_register_all_routes()
