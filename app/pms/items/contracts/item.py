# app/pms/items/contracts/item.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ShelfLifeUnit = Literal["DAY", "WEEK", "MONTH", "YEAR"]
LotSourcePolicy = Literal["INTERNAL_ONLY", "SUPPLIER_ONLY"]
ExpiryPolicy = Literal["NONE", "REQUIRED"]


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


def _norm_text(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


def _is_required_expiry_policy(v: object) -> bool:
    return str(v or "").upper() == "REQUIRED"


class ItemBase(_Base):
    sku: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    # 兼容输出字段：barcode 等同 primary_barcode
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None
    primary_barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool = True
    supplier_id: Annotated[int | None, Field(default=None)] = None

    lot_source_policy: Annotated[LotSourcePolicy | None, Field(default=None)] = None
    expiry_policy: Annotated[ExpiryPolicy | None, Field(default=None)] = None
    derivation_allowed: Annotated[bool | None, Field(default=None)] = None
    uom_governance_enabled: Annotated[bool | None, Field(default=None)] = None

    shelf_life_value: Annotated[int | None, Field(default=None, gt=0)] = None
    shelf_life_unit: Annotated[ShelfLifeUnit | None, Field(default=None)] = None

    # 兼容输出字段：事实来源已切到 base item_uom.net_weight_kg
    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator(
        "sku",
        "name",
        "spec",
        "barcode",
        "primary_barcode",
        "brand",
        "category",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)


class ItemCreate(_Base):
    """
    Create Item（SKU 由调用方显式输入）：
    - 必须传 sku；SKU 编码页只负责生成候选 SKU，最终由商品创建合同写入 items.sku
    - 不接受 barcode 输入；主条码请走 /item-barcodes
    - 不接受 weight_kg 输入；基础包装净重请走 item_uoms（base uom）

    Phase M-3：
    - items.case_ratio/case_uom 已删除；包装单位请走 item_uoms
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    sku: Annotated[str, Field(min_length=1, max_length=64)]
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
        "sku",
        "name",
        "spec",
        "brand",
        "category",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)


class ItemUpdate(_Base):
    """
    Patch Item：

    - 不开放 sku 变更
    - 不接受 barcode / has_shelf_life
    - 不接受 weight_kg；基础包装净重请改 item_uoms
    - nullable 字段支持显式传 null 清空
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )

    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool | None = None
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

    @model_validator(mode="after")
    def _at_least_one(self) -> "ItemUpdate":
        if not self.model_fields_set:
            raise ValueError("至少提供一个更新字段")
        return self


class ItemOut(ItemBase):
    id: int
    supplier_name: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None

    requires_batch: bool = True
    requires_dates: bool = True

    @model_validator(mode="after")
    def _derive_require_flags(self) -> "ItemOut":
        req = _is_required_expiry_policy(self.expiry_policy)
        self.requires_batch = bool(req)
        self.requires_dates = bool(req)
        return self


__all__ = [
    "ItemBase",
    "ItemCreate",
    "ItemUpdate",
    "ItemOut",
]
