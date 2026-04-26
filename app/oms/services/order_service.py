# app/oms/services/order_service.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.oms.services.order_ingest_service import OrderIngestService
from app.oms.services.order_trace_helper import get_trace_id_for_order_ref


class OrderService:
    """
    订单服务门面（Facade）：

    当前保留能力：
    - ingest_raw
    - ingest
    - get_trace_id_for_order

    已退役能力：
    - enter_pickable
    - cancel
    - reserve

    说明：
    - OMS 负责订单解析与订单事实；
    - WMS 出库不再走旧 pick-task / reserve 主线；
    - 若仍有旧调用点触发 enter_pickable / cancel / reserve，应尽快迁走。
    """

    # -------- Ingest -------- #

    @staticmethod
    async def ingest_raw(
        session: AsyncSession,
        *,
        platform: str,
        store_code: str,
        payload: Dict[str, Any],
        trace_id: Optional[str] = None,
    ) -> dict:
        return await OrderIngestService.ingest_raw(
            session,
            platform=platform,
            store_code=store_code,
            payload=payload,
            trace_id=trace_id,
        )

    @staticmethod
    async def ingest(
        session: AsyncSession,
        *,
        platform: str,
        store_code: str,
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
            store_code=store_code,
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
        store_code: str,
        ref: str,
    ) -> Optional[str]:
        return await get_trace_id_for_order_ref(
            session,
            platform=platform,
            store_code=store_code,
            ref=ref,
        )

    # -------- Retired legacy methods -------- #

    @staticmethod
    async def enter_pickable(
        session: AsyncSession,
        *,
        platform: str,
        store_code: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        raise RuntimeError(
            "OrderService.enter_pickable is retired. "
            "OMS no longer enters WMS pick-task flow. "
            "Use the new outbound event-based WMS submit flow instead."
        )

    @staticmethod
    async def cancel(
        session: AsyncSession,
        *,
        platform: str,
        store_code: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        raise RuntimeError(
            "OrderService.cancel is retired with the old pick-task flow. "
            "Use the new outbound/manual event flow instead."
        )

    @staticmethod
    async def reserve(
        session: AsyncSession,
        *,
        platform: str,
        store_code: str,
        ref: str,
        lines: Sequence[Mapping[str, Any]],
        trace_id: Optional[str] = None,
    ) -> dict:
        raise RuntimeError(
            "OrderService.reserve is retired. "
            "The old reserve/pick-task flow has been removed."
        )
