# app/tms/reports/router.py
#
# 分拆说明：
# - 本文件是 TMS / Reports 的路由装配入口。
# - shipping reports 相关入口正从历史 app/api/routers 收口到 TMS 语义下；
# - 当前阶段 list / options / aggregates 均已切到 app/tms/reports/；
# - 不改 URL，只调整物理归属与查询口径。
from __future__ import annotations

from fastapi import APIRouter

from app.tms.reports import routes_aggregates
from app.tms.reports import routes_list
from app.tms.reports import routes_options

router = APIRouter(tags=["shipping-reports"])


def _register_all_routes() -> None:
    routes_aggregates.register(router)
    routes_list.register(router)
    routes_options.register(router)


_register_all_routes()
