from __future__ import annotations

from fastapi import APIRouter

# 只保留一处模块导入，避免重复定义（ruff F811）
from . import inbound, outbound, snapshot, stock

api_router = APIRouter()

# 路由注册顺序可按你的偏好；这里与之前一致
api_router.include_router(snapshot.router)
api_router.include_router(stock.router)
api_router.include_router(outbound.router)
api_router.include_router(inbound.router)

__all__ = ["api_router"]
