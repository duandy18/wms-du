from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.contracts.shipping_cost import ShippingCostResponse
from app.finance.sources.shipping_cost_source import ShippingCostSource


class FinanceShippingCostService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_shipping_costs(
        self,
        *,
        from_date: date,
        to_date: date,
        platform: str = "",
        shop_id: str = "",
    ) -> ShippingCostResponse:
        source = ShippingCostSource(self.session)
        data = await source.fetch(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
        )
        return ShippingCostResponse(**data)
