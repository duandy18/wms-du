# app/oms/services/order_service.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.services.order_ingest_service import OrderIngestService
from app.wms.outbound.services.order_reserve_flow import OrderPickFlow  # Phase 5：已收口为 enter_pickable / cancel
from app.oms.services.order_trace_helper import get_trace_id_for_order_ref


class OrderService:
    """
    订单服务门面（Facade）：

    - 实际业务逻辑拆分在：
        * OrderIngestService：ingest_raw / ingest / 路由
        * OrderPickFlow：enter_pickable / cancel（进入拣货主线与取消；不做预占）
        * OrderTraceHelper：get_trace_id_for_order_ref
    - 对外保持兼容：tests / platform_events 继续 import OrderService 即可。

    Phase 5 约束（硬）：
    - 彻底消除“预占”概念：系统不做订单预占，不存在 reserve 作为阶段机。
    - 若外部仍调用 reserve()，语义等同于 enter_pickable（兼容别名）。
    """

    # -------- Ingest -------- #

    @staticmethod
    async def ingest_raw(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict:
        return await OrderIngestService.ingest_raw(
            session,
            platform=platform,
            shop_id=shop_id,
            payload=payload,
            trace_id=trace_id,
        )

    @staticmethod
    async def ingest(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ext_order_no: str,
        occurred_at: Optional[datetime] = None,
        buyer_name: Optional[str] = None,
        buyer_phone: Optional[str] = None,
        order_amount: Decimal | int | float | str = 0,
        pay_amount: Decimal | int | float | str = 0,
        items: Sequence[Mapping[str, Any]] = (),
        address: Optional[Mapping[str, str]] = None,
        extras: Optional[Mapping[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> dict:
        return await OrderIngestService.ingest(
            session,
            platform=platform,
            shop_id=shop_id,
            ext_order_no=ext_order_no,
            occurred_at=occurred_at,
            buyer_name=buyer_name,
            buyer_phone=buyer_phone,
            order_amount=order_amount,
            pay_amount=pay_amount,
            items=items,
            address=address,
            extras=extras,
            trace_id=trace_id,
        )

    # -------- Trace Helper -------- #

    @staticmethod
    async def get_trace_id_for_order(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
    ) -> Optional[str]:
        return await get_trace_id_for_order_ref(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
        )

    # -------- Enter Pickable / Cancel -------- #

    @staticmethod
    async def enter_pickable(
        session: AsyncSession,
        *,
        platform: str,
        shop_id: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        """
        Phase 5：进入拣货主线（生成 pick task + 入队拣货单打印），不做库存裁决/不做预占。
        """
        return await OrderPickFlow.enter_pickable(
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
        return await OrderPickFlow.cancel(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            trace_id=trace_id,
        )

    # -------- Compatibility Alias (legacy) -------- #

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
        """
        兼容别名：历史调用点的 reserve() 语义等同于 enter_pickable()。

        注意：此处不引入“预占”概念，仅为兼容外部事件/旧测试命名。
        """
        return await OrderService.enter_pickable(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            trace_id=trace_id,
        )
