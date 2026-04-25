from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.contracts.order_sales import OrderSalesResponse
from app.finance.sources.order_sales_source import OrderSalesSource


class FinanceOrderSalesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_order_sales(
        self,
        *,
        from_date: date,
        to_date: date,
        platform: str = "",
        shop_id: str = "",
    ) -> OrderSalesResponse:
        source = OrderSalesSource(self.session)
        data = await source.fetch(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
        )
        return OrderSalesResponse(**data)
