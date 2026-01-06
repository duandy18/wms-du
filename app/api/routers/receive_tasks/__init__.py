# app/api/routers/receive_tasks/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from . import base, from_sources, supplement

router = APIRouter(prefix="/receive-tasks", tags=["receive-tasks"])

# 子路由注册（保持 URL 不变）
base.register(router)
from_sources.register(router)
supplement.register(router)
