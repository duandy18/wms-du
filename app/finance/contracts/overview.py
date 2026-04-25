from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class FinanceOverviewSummary(BaseModel):
    revenue: Decimal
    purchase_cost: Decimal
    shipping_cost: Decimal
    gross_profit: Decimal
    gross_margin: Decimal | None = None
    fulfillment_ratio: Decimal | None = None


class FinanceOverviewDailyRow(BaseModel):
    day: date
    revenue: Decimal
    purchase_cost: Decimal
    shipping_cost: Decimal
    gross_profit: Decimal
    gross_margin: Decimal | None = None
    fulfillment_ratio: Decimal | None = None


class FinanceOverviewResponse(BaseModel):
    summary: FinanceOverviewSummary
    daily: list[FinanceOverviewDailyRow]
