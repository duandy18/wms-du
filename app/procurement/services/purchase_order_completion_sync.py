# app/procurement/services/purchase_order_completion_sync.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.procurement.repos.purchase_order_line_completion_repo import (
    apply_completion_delta_for_event,
)


async def sync_purchase_completion_for_inbound_event(
    session: AsyncSession,
    *,
    event_id: int,
    occurred_at: datetime,
) -> None:
    """
    procurement 域拥有 purchase_order_line_completion 读模型维护权。

    当前阶段这条 service 边界只做一件事：
    - 接收 WMS 已经落库成功的正式采购入库事件
    - 依据 event_id，把本次新增 qty_base 同步进 completion 读表

    注意：
    - 这里是 procurement 对 WMS 事实事件的消费边界
    - WMS 调到这一层即可，不再直接 import procurement repo
    """
    await apply_completion_delta_for_event(
        session,
        event_id=int(event_id),
        occurred_at=occurred_at,
    )


__all__ = [
    "sync_purchase_completion_for_inbound_event",
]
