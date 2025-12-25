# app/api/routers/stores.py
from __future__ import annotations

from fastapi import APIRouter

# 路由注册（拆分后的实现）
from app.api.routers import stores_routes_bindings
from app.api.routers import stores_routes_crud
from app.api.routers import stores_routes_platform_auth

# 兼容导出：合同测试/旧 import 可能直接从 stores 模块 import schema/类型
from app.api.routers.stores_helpers import (
    check_perm as _check_perm,  # 向后兼容旧名字
    ensure_store_exists as _ensure_store_exists,
    ensure_warehouse_exists as _ensure_warehouse_exists,
)
from app.api.routers.stores_schemas import (
    PlatformStr,
    BindWarehouseIn,
    BindWarehouseOut,
    BindingDeleteOut,
    BindingUpdateIn,
    BindingUpdateOut,
    DefaultWarehouseOut,
    StoreCreateIn,
    StoreCreateOut,
    StoreDetailOut,
    StoreListItem,
    StoreListOut,
    StorePlatformAuthOut,
    StoreUpdateIn,
    StoreUpdateOut,
)

router = APIRouter(tags=["stores"])


def _register_all_routes() -> None:
    stores_routes_crud.register(router)
    stores_routes_bindings.register(router)
    stores_routes_platform_auth.register(router)


_register_all_routes()

# 显式声明可导出符号（可读性 + 合同稳定）
__all__ = [
    "router",
    "PlatformStr",
    "StoreCreateIn",
    "StoreCreateOut",
    "StoreListItem",
    "StoreListOut",
    "StoreUpdateIn",
    "StoreUpdateOut",
    "BindWarehouseIn",
    "BindWarehouseOut",
    "BindingUpdateIn",
    "BindingUpdateOut",
    "BindingDeleteOut",
    "DefaultWarehouseOut",
    "StoreDetailOut",
    "StorePlatformAuthOut",
    "_check_perm",
    "_ensure_store_exists",
    "_ensure_warehouse_exists",
]
