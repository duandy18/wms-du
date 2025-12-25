# app/services/order_reserve_flow.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_reserve_flow_cancel import cancel_flow
from app.services.order_reserve_flow_reserve import reserve_flow, resolve_warehouse_for_order


class OrderReserveFlow:
    """
    订单预占 / 取消流程中控：

    - reserve：构造/更新软预占 + anti-oversell + ORDER_RESERVED 事件 + status；
    - cancel：释放软预占 + ORDER_CANCELED 事件 + status。
    """

    @staticmethod
    async def _resolve_warehouse_for_order(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
    ) -> int:
        return await resolve_warehouse_for_order(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
        )

    @staticmethod
    async def reserve(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        return await reserve_flow(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            trace_id=trace_id,
        )

    @staticmethod
    async def cancel(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        return await cancel_flow(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            trace_id=trace_id,
        )
