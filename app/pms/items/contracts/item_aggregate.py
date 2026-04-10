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
    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool = True
    supplier_id: int | None = None

    lot_source_policy: LotSourcePolicy | None = None
    expiry_policy: ExpiryPolicy | None = None
    derivation_allowed: bool | None = None
    uom_governance_enabled: bool | None = None

    shelf_life_value: Annotated[int | None, Field(default=None, gt=0)] = None
    shelf_life_unit: Annotated[ShelfLifeUnit | None, Field(default=None)] = None

    @field_validator(
        "name",
        "spec",
        "brand",
        "category",
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


class ItemAggregatePayload(_Base):
    item: AggregateItemInput
    uoms: list[AggregateUomInput]
    barcodes: list[AggregateBarcodeInput]

    @model_validator(mode="after")
    def _validate_shape(self) -> "ItemAggregatePayload":
        if not self.uoms:
            raise ValueError("uoms 不能为空")

        uom_keys = [str(x.uom_key) for x in self.uoms]
        if len(set(uom_keys)) != len(uom_keys):
            raise ValueError("uom_key 不能重复")

        base_rows = [x for x in self.uoms if x.is_base]
        if len(base_rows) != 1:
            raise ValueError("必须且只能提供一个基础包装")

        base = base_rows[0]
        if int(base.ratio_to_base) != 1:
            raise ValueError("基础包装的 ratio_to_base 必须为 1")

        purchase_defaults = [x for x in self.uoms if x.is_purchase_default]
        inbound_defaults = [x for x in self.uoms if x.is_inbound_default]
        outbound_defaults = [x for x in self.uoms if x.is_outbound_default]

        if len(purchase_defaults) > 1:
            raise ValueError("采购默认包装最多只能有一个")
        if len(inbound_defaults) > 1:
            raise ValueError("入库默认包装最多只能有一个")
        if len(outbound_defaults) > 1:
            raise ValueError("出库默认包装最多只能有一个")

        valid_uom_keys = set(uom_keys)

        primary_barcodes = [x for x in self.barcodes if x.is_primary]
        if len(primary_barcodes) > 1:
            raise ValueError("主条码最多只能有一个")

        for bc in self.barcodes:
            if str(bc.bind_uom_key) not in valid_uom_keys:
                raise ValueError(f"barcode 绑定的 uom_key 不存在: {bc.bind_uom_key}")

        return self


class AggregateBarcodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: int
    item_uom_id: int
    barcode: str
    symbology: str
    active: bool
    is_primary: bool


class ItemAggregateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item: ItemOut
    uoms: list[ItemUomOut]
    barcodes: list[AggregateBarcodeOut]
