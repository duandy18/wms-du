# app/api/routers/receive_tasks/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from . import base, from_sources, supplement

router = APIRouter(prefix="/receive-tasks", tags=["receive-tasks"])

# 子路由注册（保持 URL 不变）
# 重要：先注册静态路径（/supplements），避免被 /{task_id} 等动态路由抢匹配导致 422
supplement.register(router)
base.register(router)
from_sources.register(router)
