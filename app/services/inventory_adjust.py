# app/services/inventory_adjust.py
"""
LEGACY SHIM: inventory_adjust.adjust

用途：
- 仅用于兼容历史测试 / 旧调用代码中依赖的 `inventory_adjust.adjust` 接口。
- 内部实现已经完全走 v2 库存引擎：统一委托给 StockService.adjust。
- 新业务代码禁止再依赖本模块，应直接使用 StockService.adjust。

特性：
- 按 MovementType.COUNT 记账（盘点/调账语义）；
- 支持基于 location_id 的调整，用于兼容仍未移除 location_id 的测试场景；
- 不管理事务（事务边界由上层控制）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MovementType
from app.services.stock_service import StockService


async def adjust(
    session: AsyncSession,
    *,
    item_id: int,
    location_id: int,
    delta: int,
    ref: str,
    occurred_at: Optional[datetime] = None,
) -> dict:
    """
    兼容性库存调整（COUNT）——仅供历史测试使用。
    """
    svc = StockService()
    return await svc.adjust(
        session=session,
        item_id=item_id,
        location_id=location_id,
        delta=delta,
        reason=MovementType.COUNT,
        ref=ref,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
