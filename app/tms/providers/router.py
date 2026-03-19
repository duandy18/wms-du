# app/tms/providers/router.py
# 分拆说明：
# - 本文件是 TMS / providers 子域路由壳；
# - 统一装配 providers 读写接口与 contacts 子资源接口；
# - 当前 URL 保持 /shipping-providers 与 /shipping-provider-contacts 不变。
from __future__ import annotations

from fastapi import APIRouter

from . import routes_contacts, routes_read, routes_write

router = APIRouter(tags=["shipping-providers"])


def _register_all_routes() -> None:
    routes_read.register(router)
    routes_write.register(router)
    routes_contacts.register(router)


_register_all_routes()
