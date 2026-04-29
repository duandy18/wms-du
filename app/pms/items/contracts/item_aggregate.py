# app/pms/items/contracts/item_aggregate.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.pms.items.contracts.item import (
    ExpiryPolicy,
    ItemOut,
    LotSourcePolicy,
    ShelfLifeUnit,
)
from app.pms.items.contracts.item_uom import ItemUomOut


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


def _norm_text(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class AggregateItemInput(_Base):
    sku: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    brand_id: int | None = None
    category_id: int | None = None

    enabled: bool = True
    supplier_id: int | None = None

    lot_source_policy: LotSourcePolicy | None = None
    expiry_policy: ExpiryPolicy | None = None
    derivation_allowed: bool | None = None
    uom_governance_enabled: bool | None = None

    shelf_life_value: Annotated[int | None, Field(default=None, gt=0)] = None
    shelf_life_unit: Annotated[ShelfLifeUnit | None, Field(default=None)] = None

    @field_validator(
        "sku",
        "name",
        "spec",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)


class AggregateUomInput(_Base):
    id: int | None = None
    uom_key: Annotated[str, Field(min_length=1, max_length=64)]

    uom: Annotated[str, Field(min_length=1, max_length=16)]
    ratio_to_base: Annotated[int, Field(ge=1)]
    display_name: Annotated[str | None, Field(default=None, max_length=32)] = None
    net_weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    is_base: bool = False
    is_purchase_default: bool = False
    is_inbound_default: bool = False
    is_outbound_default: bool = False

    @field_validator(
        "uom_key",
        "uom",
        "display_name",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)


BarcodeSymbology = Literal["EAN13", "UPC", "UPC12", "EAN8", "GS1", "CUSTOM"]


class AggregateBarcodeInput(_Base):
    id: int | None = None

    barcode: Annotated[str, Field(min_length=1, max_length=128)]
    symbology: BarcodeSymbology = "CUSTOM"
    active: bool = True
    is_primary: bool = False

    bind_uom_key: Annotated[str, Field(min_length=1, max_length=64)]

    @field_validator(
        "barcode",
        "bind_uom_key",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)

    @model_validator(mode="after")
    def _primary_must_be_active(self) -> "AggregateBarcodeInput":
        if self.is_primary and not self.active:
            raise ValueError("primary barcode must be active")
        return self


class AggregateBarcodeOut(_Base):
    id: int
    item_id: int
    item_uom_id: int
    barcode: str
    symbology: str
    active: bool
    is_primary: bool
    created_at: object | None = None
    updated_at: object | None = None


class ItemAggregatePayload(_Base):
    item: AggregateItemInput
    uoms: list[AggregateUomInput]
    barcodes: list[AggregateBarcodeInput]

    @model_validator(mode="after")
    def _validate_shape(self) -> "ItemAggregatePayload":
        if not self.uoms:
            raise ValueError("at least one item_uom is required")
        if sum(1 for u in self.uoms if u.is_base) != 1:
            raise ValueError("exactly one base uom is required")
        if sum(1 for u in self.uoms if u.is_purchase_default) != 1:
            raise ValueError("exactly one purchase default uom is required")
        if sum(1 for u in self.uoms if u.is_inbound_default) != 1:
            raise ValueError("exactly one inbound default uom is required")
        if sum(1 for u in self.uoms if u.is_outbound_default) != 1:
            raise ValueError("exactly one outbound default uom is required")
        return self


class ItemAggregateOut(_Base):
    item: ItemOut
    uoms: list[ItemUomOut]
    barcodes: list[AggregateBarcodeOut]
