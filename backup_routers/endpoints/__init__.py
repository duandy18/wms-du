# app/api/endpoints/__init__.py
"""
兼容层（legacy shim）：
- 聚合并导出 `api_router`，把新的 `app.routers.*` 路由纳入老的 API 路由树；
- 同时“尽力挂载”旧的 endpoints 模块（若仍存在且可导入）；
- 让 `app.main` 里 `from app.api.endpoints import api_router` 不需要改动。
"""

from __future__ import annotations

import logging
from fastapi import APIRouter

log = logging.getLogger("wmsdu.api_compat")

api_router = APIRouter()

# ============================================================
# 新版路由（首选入口）
# ============================================================
# /stores/*
try:
    from app.routers.store import router as store_router  # type: ignore

    api_router.include_router(store_router)
    log.info("api_router: mounted new /stores/*")
except Exception as e:
    log.debug("api_router: /stores/* not mounted: %s", e)

# /snapshot/*
try:
    from app.routers import admin_snapshot  # type: ignore

    api_router.include_router(admin_snapshot.router)
    log.info("api_router: mounted new /snapshot/*")
except Exception as e:
    log.debug("api_router: /snapshot/* not mounted: %s", e)

# /orders/*（reserve/cancel/ship/preview-visible）
try:
    from app.routers import orders as orders_router  # type: ignore

    api_router.include_router(orders_router.router)
    log.info("api_router: mounted new /orders/*")
except Exception as e:
    log.debug("api_router: /orders/* not mounted: %s", e)

# /webhook/*（平台回调）
try:
    from app.routers import webhooks as webhooks_router  # type: ignore

    api_router.include_router(webhooks_router.router)
    log.info("api_router: mounted new /webhook/*")
except Exception as e:
    log.debug("api_router: /webhook/* not mounted: %s", e)

# /auth/*（用户/鉴权）
try:
    from app.routers import users as users_router  # type: ignore

    api_router.include_router(users_router.router)
    log.info("api_router: mounted new /auth/*")
except Exception as e:
    log.debug("api_router: /auth/* not mounted: %s", e)


# ============================================================
# 旧版 endpoints（best-effort，按需保留）
# 说明：
# - 若这些模块依然存在且 import 成功，就把它们的 router 也挂上；
# - 便于你逐步删减/迁移老的 API 模块，而不影响现在的访问。
# ============================================================


def _mount_legacy(modpath: str, attr: str = "router") -> None:
    try:
        mod = __import__(modpath, fromlist=[attr])
        r = getattr(mod, attr, None)
        if r is not None:
            api_router.include_router(r)
            log.info("api_router: mounted legacy %s", modpath)
    except Exception as e:
        log.debug("api_router: legacy %s not mounted: %s", modpath, e)


# 逐个尝试（存在就挂，不存在就跳过 → 无侵入）
for _m in (
    "app.api.endpoints.inbound",
    "app.api.endpoints.outbound",
    "app.api.endpoints.snapshot",
    "app.api.endpoints.inventory",
    "app.api.endpoints.stocks",
    "app.api.endpoints.stock",
    "app.api.endpoints.stock_batch",
    "app.api.endpoints.stock_transfer",
    "app.api.endpoints.stock_inventory",
    "app.api.endpoints.stock_ledger",
    "app.api.endpoints.items",
    "app.api.endpoints.batch",
    "app.api.endpoints.roles",
    "app.api.endpoints.permissions",
    "app.api.endpoints.users",
    "app.api.endpoints.diag",
):
    _mount_legacy(_m)

# 提示：所有新开发应优先落在 app/routers/* ，此层仅用于兼容老路径。
