from __future__ import annotations

from datetime import date, datetime
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


class ShippingCostProviderRow(BaseModel):
    shipping_provider_id: int | None = None
    shipping_provider_code: str | None = None
    shipping_provider_name: str | None = None
    shipment_count: int
    estimated_shipping_cost: Decimal
    billed_shipping_cost: Decimal


class ShippingCostShopRow(BaseModel):
    platform: str
    shop_id: str
    shop_name: str | None = None
    shipment_count: int
    estimated_shipping_cost: Decimal
    billed_shipping_cost: Decimal


class ShippingCostResponse(BaseModel):
    summary: ShippingCostSummary
    daily: list[ShippingCostDailyRow]
    # 保持既有 summary 接口结构，行字段已切到 shipping_provider_*。
    by_carrier: list[ShippingCostProviderRow]
    by_shop: list[ShippingCostShopRow]


class ShippingCostLedgerRow(BaseModel):
    shipping_record_id: int

    platform: str
    shop_id: str
    shop_name: str | None = None

    order_ref: str
    package_no: int
    tracking_no: str | None = None

    warehouse_id: int
    warehouse_name: str

    shipping_provider_id: int
    shipping_provider_code: str | None = None
    shipping_provider_name: str | None = None

    shipped_time: datetime
    shipped_date: date

    dest_province: str | None = None
    dest_city: str | None = None

    gross_weight_kg: Decimal | None = None
    cost_estimated: Decimal | None = None


class ShippingCostLedgerResponse(BaseModel):
    rows: list[ShippingCostLedgerRow]


class ShippingCostLedgerShopOption(BaseModel):
    platform: str
    shop_id: str
    shop_name: str | None = None


class ShippingCostLedgerWarehouseOption(BaseModel):
    warehouse_id: int
    warehouse_name: str


class ShippingCostLedgerProviderOption(BaseModel):
    shipping_provider_id: int
    shipping_provider_code: str | None = None
    shipping_provider_name: str | None = None


class ShippingCostLedgerOptionsResponse(BaseModel):
    shops: list[ShippingCostLedgerShopOption]
    warehouses: list[ShippingCostLedgerWarehouseOption]
    providers: list[ShippingCostLedgerProviderOption]
