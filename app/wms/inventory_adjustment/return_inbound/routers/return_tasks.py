# Split note:
# 本文件是 inventory_adjustment.return_inbound 的本地路由装配入口。
# 第二刀开始后，这里不再直接 re-export 旧 router，而是改为组装本目录下的真实 router 文件。

from __future__ import annotations

from fastapi import APIRouter

from .order_refs import register_order_refs
from .tasks import register_tasks


def build_router() -> APIRouter:
    router = APIRouter(prefix="/return-tasks", tags=["return-tasks"])
    register_order_refs(router)
    register_tasks(router)
    return router


router = build_router()

__all__ = ["router", "build_router"]
