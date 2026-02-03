# app/services/order_reserve_flow.py
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_reserve_flow_cancel import cancel_flow
from app.services.order_reserve_flow_reserve import reserve_flow, resolve_warehouse_for_order


class OrderReserveFlow:
    """
    订单进入仓内执行态 / 取消流程中控（历史文件名保留）：

    ✅ 当前语义（蓝皮书一致）：
    - reserve：enter_pickable（自动生成 pick task + 入队拣货单打印），不做库存裁决/不做库存校验；
    - cancel：取消（取消订单执行态与审计动作）。

    注意：本阶段不引入任何旧链路的占用/锁定语义。
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
        # 兼容旧调用点：reserve 已被收敛为 enter_pickable
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
