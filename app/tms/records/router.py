# app/tms/records/router.py
#
# 分拆说明：
# - 本文件是 TMS / Records 的路由装配入口。
# - logistics ledger（shipping_records）相关只读接口已物理收口到 app/tms/records/；
# - 状态更新入口已下线，不再注册。
from __future__ import annotations

from fastapi import APIRouter

from app.tms.records import routes_read

router = APIRouter(tags=["shipping-records"])


def _register_all_routes() -> None:
    routes_read.register(router)


_register_all_routes()
