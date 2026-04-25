from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.finance.contracts.overview import (
    FinanceOverviewDailyRow,
    FinanceOverviewResponse,
    FinanceOverviewSummary,
)
from app.finance.services.common import ratio
from app.finance.sources.order_sales_source import OrderSalesSource
from app.finance.sources.purchase_cost_source import PurchaseCostSource
from app.finance.sources.shipping_cost_source import ShippingCostSource


class FinanceOverviewService:
    """
    综合分析服务。

    边界：
    - 综合分析是唯一同时读取订单销售 / 采购成本 / 物流成本三条来源的财务服务；
    - 仍然只读，不写任何来源域业务事实；
    - 第一阶段 shipping_cost 使用 shipping_records.cost_estimated 预估物流成本。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_overview(
        self,
        *,
        from_date: date,
        to_date: date,
        platform: str = "",
        shop_id: str = "",
    ) -> FinanceOverviewResponse:
        order_data = await OrderSalesSource(self.session).fetch(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
        )
        purchase_data = await PurchaseCostSource(self.session).fetch(
            from_date=from_date,
            to_date=to_date,
        )
        shipping_data = await ShippingCostSource(self.session).fetch(
            from_date=from_date,
            to_date=to_date,
            platform=platform,
            shop_id=shop_id,
        )

        order_daily = {row["day"]: row for row in order_data["daily"]}
        purchase_daily = {row["day"]: row for row in purchase_data["daily"]}
        shipping_daily = {row["day"]: row for row in shipping_data["daily"]}

        days = sorted(set(order_daily) | set(purchase_daily) | set(shipping_daily))

        daily_rows: list[FinanceOverviewDailyRow] = []
        for day in days:
            revenue = Decimal(str(order_daily.get(day, {}).get("revenue", 0)))
            purchase_cost = Decimal(str(purchase_daily.get(day, {}).get("purchase_amount", 0)))
            shipping_cost = Decimal(
                str(shipping_daily.get(day, {}).get("estimated_shipping_cost", 0))
            )
            gross_profit = revenue - purchase_cost - shipping_cost
            daily_rows.append(
                FinanceOverviewDailyRow(
                    day=day,
                    revenue=revenue,
                    purchase_cost=purchase_cost,
                    shipping_cost=shipping_cost,
                    gross_profit=gross_profit,
                    gross_margin=ratio(gross_profit, revenue),
                    fulfillment_ratio=ratio(shipping_cost, revenue),
                )
            )

        revenue_total = sum((row.revenue for row in daily_rows), Decimal("0"))
        purchase_total = sum((row.purchase_cost for row in daily_rows), Decimal("0"))
        shipping_total = sum((row.shipping_cost for row in daily_rows), Decimal("0"))
        gross_total = revenue_total - purchase_total - shipping_total

        summary = FinanceOverviewSummary(
            revenue=revenue_total,
            purchase_cost=purchase_total,
            shipping_cost=shipping_total,
            gross_profit=gross_total,
            gross_margin=ratio(gross_total, revenue_total),
            fulfillment_ratio=ratio(shipping_total, revenue_total),
        )

        return FinanceOverviewResponse(summary=summary, daily=daily_rows)
