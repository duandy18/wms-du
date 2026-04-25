from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.contracts.purchase_cost import PurchaseCostResponse
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
