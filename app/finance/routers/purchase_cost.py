from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.finance.contracts.purchase_cost import PurchaseCostResponse
from app.finance.services.common import ensure_default_range, parse_date_param
from app.finance.services.purchase_cost_service import FinancePurchaseCostService
from app.user.deps.auth import get_current_user


def register(router: APIRouter) -> None:
    @router.get(
        "/purchase-costs",
        response_model=PurchaseCostResponse,
        summary="财务分析采购成本",
    )
    async def get_finance_purchase_costs(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，默认最近 30 天"),
        to_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
    ) -> PurchaseCostResponse:
        _ = current_user
        from_dt, to_dt = await ensure_default_range(
            session,
            from_dt=parse_date_param(from_date),
            to_dt=parse_date_param(to_date),
        )
        return await FinancePurchaseCostService(session).get_purchase_costs(
            from_date=from_dt,
            to_date=to_dt,
        )
