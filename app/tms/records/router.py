# app/tms/records/router.py
#
# 分拆说明：
# - 本文件是 TMS / Records 的路由壳。
# - 目标是把 shipping_records 相关入口从历史 app/api/routers 外壳中收口到 TMS 语义下。
# - 当前不改 URL，只调整物理归属。
from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import shipping_records_routes_read
from app.api.routers import shipping_records_routes_status

router = APIRouter(tags=["shipping-records"])


def _register_all_routes() -> None:
    shipping_records_routes_read.register(router)
    shipping_records_routes_status.register(router)


_register_all_routes()
