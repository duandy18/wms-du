from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.finance.contracts.overview import FinanceOverviewResponse
from app.finance.services.common import (
    clean_platform,
    clean_shop_id,
    ensure_default_range,
    parse_date_param,
)
from app.finance.services.overview_service import FinanceOverviewService
from app.user.deps.auth import get_current_user


def register(router: APIRouter) -> None:
    @router.get(
        "/overview",
        response_model=FinanceOverviewResponse,
        summary="财务分析综合分析",
    )
    async def get_overview(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，默认最近 30 天"),
        to_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
        platform: str | None = Query(None, description="平台过滤，可选"),
        shop_id: str | None = Query(None, description="店铺过滤，可选"),
    ) -> FinanceOverviewResponse:
        _ = current_user
        from_dt, to_dt = await ensure_default_range(
            session,
            from_dt=parse_date_param(from_date),
            to_dt=parse_date_param(to_date),
        )
        return await FinanceOverviewService(session).get_overview(
            from_date=from_dt,
            to_date=to_dt,
            platform=clean_platform(platform),
            shop_id=clean_shop_id(shop_id),
        )
