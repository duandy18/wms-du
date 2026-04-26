from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.finance.contracts.order_sales import OrderSalesResponse
from app.finance.services.common import (
    clean_platform,
    clean_store_code,
    ensure_default_range,
    parse_date_param,
)
from app.finance.services.order_sales_service import FinanceOrderSalesService
from app.user.deps.auth import get_current_user


def register(router: APIRouter) -> None:
    @router.get(
        "/order-sales",
        response_model=OrderSalesResponse,
        summary="财务分析订单销售",
    )
    async def get_finance_order_sales(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，默认最近 30 天"),
        to_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
        platform: str | None = Query(None, description="平台过滤，可选"),
        store_code: str | None = Query(None, description="店铺过滤，可选"),
    ) -> OrderSalesResponse:
        _ = current_user
        from_dt, to_dt = await ensure_default_range(
            session,
            from_dt=parse_date_param(from_date),
            to_dt=parse_date_param(to_date),
        )
        return await FinanceOrderSalesService(session).get_order_sales(
            from_date=from_dt,
            to_date=to_dt,
            platform=clean_platform(platform),
            store_code=clean_store_code(store_code),
        )
