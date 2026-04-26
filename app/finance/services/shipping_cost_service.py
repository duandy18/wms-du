from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.contracts.shipping_cost import (
    ShippingCostLedgerOptionsResponse,
    ShippingCostLedgerResponse,
    ShippingCostResponse,
)
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

    async def get_shipping_ledger(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        platform: str = "",
        shop_id: str = "",
        warehouse_id: int | None = None,
        shipping_provider_id: int | None = None,
        order_keyword: str = "",
        tracking_no: str = "",
    ) -> ShippingCostLedgerResponse:
        source = ShippingCostSource(self.session)
        data = await source.fetch_shipping_ledger(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            shipping_provider_id=shipping_provider_id,
            order_keyword=order_keyword,
            tracking_no=tracking_no,
        )
        return ShippingCostLedgerResponse(**data)

    async def get_shipping_ledger_options(
        self,
        *,
        from_date: date | None,
        to_date: date | None,
        platform: str = "",
        shop_id: str = "",
        warehouse_id: int | None = None,
        shipping_provider_id: int | None = None,
    ) -> ShippingCostLedgerOptionsResponse:
        source = ShippingCostSource(self.session)
        data = await source.fetch_shipping_ledger_options(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
            warehouse_id=warehouse_id,
            shipping_provider_id=shipping_provider_id,
        )
        return ShippingCostLedgerOptionsResponse(**data)
