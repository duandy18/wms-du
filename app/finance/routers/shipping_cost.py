from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.finance.contracts.shipping_cost import (
    ShippingCostLedgerOptionsResponse,
    ShippingCostLedgerResponse,
    ShippingCostResponse,
)
from app.finance.services.common import (
    clean_platform,
    clean_store_code,
    ensure_default_range,
    parse_date_param,
)
from app.finance.services.shipping_cost_service import FinanceShippingCostService
from app.user.deps.auth import get_current_user


def register(router: APIRouter) -> None:
    @router.get(
        "/shipping-costs",
        response_model=ShippingCostResponse,
        summary="财务分析物流成本",
    )
    async def get_finance_shipping_costs(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，默认最近 30 天"),
        to_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，默认今天"),
        platform: str | None = Query(None, description="平台过滤，可选"),
        store_code: str | None = Query(None, description="店铺过滤，可选"),
    ) -> ShippingCostResponse:
        _ = current_user
        from_dt, to_dt = await ensure_default_range(
            session,
            from_dt=parse_date_param(from_date),
            to_dt=parse_date_param(to_date),
        )
        return await FinanceShippingCostService(session).get_shipping_costs(
            from_date=from_dt,
            to_date=to_dt,
            platform=clean_platform(platform),
            store_code=clean_store_code(store_code),
        )

    @router.get(
        "/shipping-costs/shipping-ledger/options",
        response_model=ShippingCostLedgerOptionsResponse,
        summary="财务分析物流成本明细筛选选项",
    )
    async def get_finance_shipping_ledger_options(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，可选"),
        to_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，可选"),
        platform: str | None = Query(None, description="平台过滤，可选"),
        store_code: str | None = Query(None, description="店铺过滤，可选"),
        warehouse_id: int | None = Query(None, description="仓库过滤，可选"),
        shipping_provider_id: int | None = Query(None, description="物流网点过滤，可选"),
    ) -> ShippingCostLedgerOptionsResponse:
        _ = current_user
        return await FinanceShippingCostService(session).get_shipping_ledger_options(
            from_date=parse_date_param(from_date),
            to_date=parse_date_param(to_date),
            platform=clean_platform(platform),
            store_code=clean_store_code(store_code),
            warehouse_id=warehouse_id,
            shipping_provider_id=shipping_provider_id,
        )

    @router.get(
        "/shipping-costs/shipping-ledger",
        response_model=ShippingCostLedgerResponse,
        summary="财务分析物流成本核算明细表",
    )
    async def get_finance_shipping_ledger(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，可选"),
        to_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，可选"),
        platform: str | None = Query(None, description="平台过滤，可选"),
        store_code: str | None = Query(None, description="店铺过滤，可选"),
        warehouse_id: int | None = Query(None, description="仓库过滤，可选"),
        shipping_provider_id: int | None = Query(None, description="物流网点过滤，可选"),
        order_keyword: str | None = Query(None, description="订单号 / 运单号模糊过滤，可选"),
        tracking_no: str | None = Query(None, description="运单号精确过滤，可选"),
    ) -> ShippingCostLedgerResponse:
        _ = current_user
        return await FinanceShippingCostService(session).get_shipping_ledger(
            from_date=parse_date_param(from_date),
            to_date=parse_date_param(to_date),
            platform=clean_platform(platform),
            store_code=clean_store_code(store_code),
            warehouse_id=warehouse_id,
            shipping_provider_id=shipping_provider_id,
            order_keyword=order_keyword or "",
            tracking_no=tracking_no or "",
        )
