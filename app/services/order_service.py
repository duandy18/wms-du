# app/services/order_service.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.order_ingest_service import OrderIngestService
from app.services.order_reserve_flow import OrderReserveFlow
from app.services.order_trace_helper import get_trace_id_for_order_ref


class OrderService:
    """
    订单服务门面（Facade）：

    - 实际业务逻辑拆分在：
        * OrderIngestService：ingest_raw / ingest / 路由
        * OrderReserveFlow：reserve / cancel
        * OrderTraceHelper：get_trace_id_for_order_ref
    - 对外保持兼容：路由 / tests / platform_events 继续 import OrderService 即可。
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
        scope: str = "PROD",
    ) -> dict:
        return await OrderIngestService.ingest_raw(
            session,
            platform=platform,
            shop_id=shop_id,
            payload=payload,
            trace_id=trace_id,
            scope=scope,
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
        scope: str = "PROD",
    ) -> dict:
        return await OrderIngestService.ingest(
            session,
            scope=scope,
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

    # -------- Reserve / Cancel -------- #

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
        return await OrderReserveFlow.reserve(
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
        return await OrderReserveFlow.cancel(
            session,
            platform=platform,
            shop_id=shop_id,
            ref=ref,
            lines=lines,
            trace_id=trace_id,
        )
