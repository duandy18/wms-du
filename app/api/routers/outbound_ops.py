# app/api/routers/outbound_ops.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/outbound/ops",
    tags=["outbound-ops"],
)


@router.get("")
@router.post("")
@router.get("/{path:path}")
@router.post("/{path:path}")
async def outbound_ops_legacy_stub() -> None:
    """
    旧版出库操作（legacy）占位路由。

    说明：
    - 早期版本依赖 ReservationPlanner / reservation_plan 等旧架构；
    - 当前 v3 出库链路已经统一到 OutboundService + pick/ship；
    - 为避免 ImportError & 破坏现有启动流程，这里保留一个空壳路由，
      一旦被访问，明确返回 410（Gone），提示调用方迁移到新接口。
    """
    raise HTTPException(
        status_code=410,
        detail="Legacy outbound ops API has been deprecated. "
        "Please migrate to the new outbound / pick / ship endpoints.",
    )
