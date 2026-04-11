# app/pms/public/items/contracts/item_aggregate.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.pms.items.contracts.item import ExpiryPolicy, LotSourcePolicy, ShelfLifeUnit


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class PublicAggregateItem(_Base):
    id: int
    sku: str
    name: str
    spec: str | None = None
    enabled: bool

    supplier_id: int | None = None
    brand: str | None = None
    category: str | None = None

    lot_source_policy: LotSourcePolicy
    expiry_policy: ExpiryPolicy
    derivation_allowed: bool
    uom_governance_enabled: bool

    shelf_life_value: int | None = Field(default=None, gt=0)
    shelf_life_unit: ShelfLifeUnit | None = None


class PublicAggregateUom(_Base):
    id: int
    item_id: int

    uom: str
    ratio_to_base: int

    display_name: str | None = None
    net_weight_kg: float | None = Field(default=None, ge=0)

    is_base: bool
    is_purchase_default: bool
    is_inbound_default: bool
    is_outbound_default: bool


class PublicAggregateBarcode(_Base):
    id: int
    item_id: int
    item_uom_id: int

    barcode: str
    symbology: str
    active: bool
    is_primary: bool


class PublicItemAggregateOut(_Base):
    item: PublicAggregateItem
    uoms: list[PublicAggregateUom]
    barcodes: list[PublicAggregateBarcode]
