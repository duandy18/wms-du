from __future__ import annotations
from fastapi import APIRouter

api_router = APIRouter(prefix="/api")

# ---- 核心作业 ----
from app.api.routers import scan, inbound, putaway, pick, count
api_router.include_router(scan.router, tags=["scan"])
api_router.include_router(inbound.router, tags=["inbound"])
api_router.include_router(putaway.router, tags=["putaway"])
api_router.include_router(pick.router, tags=["pick"])
api_router.include_router(count.router, tags=["count"])

# ---- 库存 / 台账 ----
from app.api.routers import stock, stock_ledger, stock_inventory, stock_batch, stock_transfer, stock_maintenance
api_router.include_router(stock.router, tags=["stock"])
api_router.include_router(stock_ledger.router, tags=["stock_ledger"])
api_router.include_router(stock_inventory.router, tags=["stock_inventory"])
api_router.include_router(stock_batch.router, tags=["stock_batch"])
api_router.include_router(stock_transfer.router, tags=["stock_transfer"])
api_router.include_router(stock_maintenance.router, tags=["stock_maintenance"])

# ---- 管理 / 统计 ----
from app.api.routers import snapshot
api_router.include_router(snapshot.router, tags=["snapshot"])

# ---- 订单 / 平台 ----
from app.api.routers import orders, webhooks, store, inventory, items
api_router.include_router(orders.router, tags=["orders"])
api_router.include_router(webhooks.router, tags=["webhook"])
api_router.include_router(store.router, tags=["stores"])
api_router.include_router(inventory.router, tags=["inventory"])
api_router.include_router(items.router, tags=["items"])

# ---- 用户 / 权限 ----
from app.api.routers import users, roles, permissions
api_router.include_router(users.router, tags=["users"])
api_router.include_router(roles.router, tags=["roles"])
api_router.include_router(permissions.router, tags=["permissions"])
