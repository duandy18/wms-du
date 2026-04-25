from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.contracts.purchase_cost import (
    PurchaseCostResponse,
    SkuPurchaseLedgerResponse,
)
from app.finance.sources.purchase_cost_source import PurchaseCostSource


class FinancePurchaseCostService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_purchase_costs(
        self,
        *,
        from_date: date,
        to_date: date,
    ) -> PurchaseCostResponse:
        source = PurchaseCostSource(self.session)
        data = await source.fetch(
            from_date=from_date,
            to_date=to_date,
        )
        return PurchaseCostResponse(**data)

    async def get_sku_purchase_ledger(
        self,
        *,
        from_date: date,
        to_date: date,
        supplier_id: int | None = None,
        item_keyword: str = "",
    ) -> SkuPurchaseLedgerResponse:
        source = PurchaseCostSource(self.session)
        data = await source.fetch_sku_purchase_ledger(
            from_date=from_date,
            to_date=to_date,
            supplier_id=supplier_id,
            item_keyword=item_keyword,
        )
        return SkuPurchaseLedgerResponse(**data)
