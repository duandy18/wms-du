from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()

# ---- 扫码聚合网关（含 trace）----
from app.api.routers import scan as scan_router  # noqa: E402

api_router.include_router(scan_router.router, tags=["scan"])

# ---- 其余业务路由（按需精简/保留）----
from app.api.routers import (  # noqa: E402
    inbound,
    putaway,
    pick,
    count,
    stock,
    stock_ledger,
    stock_inventory,
    stock_batch,
    stock_transfer,
    stock_maintenance,
    snapshot,
    orders,
    webhooks,
    store,
    inventory,
    item,
    roles,
    permissions,
    user,
)

api_router.include_router(inbound.router, tags=["inbound"])
api_router.include_router(putaway.router, tags=["putaway"])
api_router.include_router(pick.router, tags=["pick"])
api_router.include_router(count.router, tags=["count"])

api_router.include_router(stock.router, tags=["stock"])
api_router.include_router(stock_ledger.router, tags=["stock_ledger"])
api_router.include_router(stock_inventory.router, tags=["stock_inventory"])
api_router.include_router(stock_batch.router, tags=["stock_batch"])
api_router.include_router(stock_transfer.router, tags=["stock_transfer"])
api_router.include_router(stock_maintenance.router, tags=["stock_maintenance"])

api_router.include_router(snapshot.router, tags=["snapshot"])

api_router.include_router(orders.router, tags=["orders"])
api_router.include_router(webhooks.router, tags=["webhook"])
api_router.include_router(store.router, tags=["stores"])
api_router.include_router(inventory.router, tags=["inventory"])
api_router.include_router(item.router, tags=["item"])

api_router.include_router(user.router, tags=["users"])
api_router.include_router(roles.router, tags=["roles"])
api_router.include_router(permissions.router, tags=["permissions"])
