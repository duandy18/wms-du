from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ShippingCostSummary(BaseModel):
    shipment_count: int
    estimated_shipping_cost: Decimal
    billed_shipping_cost: Decimal
    cost_diff: Decimal
    adjusted_cost: Decimal


class ShippingCostDailyRow(BaseModel):
    day: date
    shipment_count: int
    estimated_shipping_cost: Decimal
    billed_shipping_cost: Decimal
    cost_diff: Decimal
    adjusted_cost: Decimal


class ShippingCostCarrierRow(BaseModel):
    carrier_code: str
    shipment_count: int
    estimated_shipping_cost: Decimal
    billed_shipping_cost: Decimal


class ShippingCostShopRow(BaseModel):
    platform: str
    shop_id: str
    shipment_count: int
    estimated_shipping_cost: Decimal
    billed_shipping_cost: Decimal


class ShippingCostResponse(BaseModel):
    summary: ShippingCostSummary
    daily: list[ShippingCostDailyRow]
    by_carrier: list[ShippingCostCarrierRow]
    by_shop: list[ShippingCostShopRow]
