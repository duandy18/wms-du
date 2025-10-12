# app/api/endpoints/__init__.py
from fastapi import APIRouter

from . import snapshot, stock, inbound  # 你已有的

# 明确把子路由模块导入为命名空间，便于 include_router 调用
from app.api.endpoints import stock_batch  # ← 关键：导入它
from app.api.endpoints import stock_inventory  # 新增
from app.api.endpoints import stock_transfer  # 新增
from app.api.endpoints import stock, stock_ledger

api_router = APIRouter()
api_router.include_router(stock.router)
api_router.include_router(stock_ledger.router)
api_router.include_router(stock_batch.router)  # ← 焊上
api_router.include_router(stock_inventory.router)
api_router.include_router(stock_transfer.router)
api_router.include_router(snapshot.router)
api_router.include_router(inbound.router)
