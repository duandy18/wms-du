from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_async_session as get_session
from app.finance.contracts.purchase_cost import (
    PurchaseCostResponse,
    SkuPurchaseLedgerOptionsResponse,
    SkuPurchaseLedgerResponse,
)
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

    @router.get(
        "/purchase-costs/sku-purchase-ledger/options",
        response_model=SkuPurchaseLedgerOptionsResponse,
        summary="财务分析 SKU 采购价格核算表筛选选项",
    )
    async def get_finance_sku_purchase_ledger_options(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        supplier_id: int | None = Query(None, description="供应商过滤，可选"),
        warehouse_id: int | None = Query(None, description="仓库过滤，可选"),
        item_keyword: str | None = Query(None, description="商品名 / SKU / item_id 过滤，可选"),
    ) -> SkuPurchaseLedgerOptionsResponse:
        _ = current_user
        return await FinancePurchaseCostService(session).get_sku_purchase_ledger_options(
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            item_keyword=item_keyword or "",
        )

    @router.get(
        "/purchase-costs/sku-purchase-ledger",
        response_model=SkuPurchaseLedgerResponse,
        summary="财务分析 SKU 采购价格核算表",
    )
    async def get_finance_sku_purchase_ledger(
        session: AsyncSession = Depends(get_session),
        current_user: Any = Depends(get_current_user),
        from_date: str | None = Query(None, description="起始日期 YYYY-MM-DD，可选"),
        to_date: str | None = Query(None, description="结束日期 YYYY-MM-DD，可选"),
        supplier_id: int | None = Query(None, description="供应商过滤，可选"),
        warehouse_id: int | None = Query(None, description="仓库过滤，可选"),
        item_keyword: str | None = Query(None, description="商品名 / SKU / item_id 过滤，可选"),
    ) -> SkuPurchaseLedgerResponse:
        _ = current_user
        from_dt = parse_date_param(from_date)
        to_dt = parse_date_param(to_date)
        return await FinancePurchaseCostService(session).get_sku_purchase_ledger(
            from_date=from_dt,
            to_date=to_dt,
            supplier_id=supplier_id,
            warehouse_id=warehouse_id,
            item_keyword=item_keyword or "",
        )
