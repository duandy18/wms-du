# app/pms/items/contracts/item_master.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ProductKind = Literal["FOOD", "SUPPLY", "OTHER"]
AttributeProductKind = Literal["FOOD", "SUPPLY", "OTHER", "COMMON"]
AttributeValueType = Literal["TEXT", "NUMBER", "OPTION", "BOOL"]


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore", populate_by_name=True)


def _trim(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


def _upper(v: object) -> object:
    return v.strip().upper() if isinstance(v, str) else v


class PmsBrandCreate(_Base):
    name_cn: Annotated[str, Field(min_length=1, max_length=128)]
    code: Annotated[str, Field(min_length=1, max_length=32)]
    sort_order: int = 0
    remark: Annotated[str | None, Field(default=None, max_length=500)] = None

    @field_validator("name_cn", "code", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)

    @field_validator("code", mode="before")
    @classmethod
    def _upper_code(cls, v: object) -> object:
        return _upper(v)


class PmsBrandUpdate(_Base):
    name_cn: Annotated[str | None, Field(default=None, max_length=128)] = None
    code: Annotated[str | None, Field(default=None, max_length=32)] = None
    sort_order: int | None = None
    remark: Annotated[str | None, Field(default=None, max_length=500)] = None

    @field_validator("name_cn", "code", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)

    @field_validator("code", mode="before")
    @classmethod
    def _upper_code(cls, v: object) -> object:
        return _upper(v)


class PmsBrandOut(_Base):
    id: int
    name_cn: str
    code: str
    is_active: bool
    is_locked: bool
    sort_order: int
    remark: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PmsCategoryCreate(_Base):
    parent_id: int | None = None
    level: Annotated[int, Field(ge=1, le=3)]
    product_kind: ProductKind
    category_name: Annotated[str, Field(min_length=1, max_length=128)]
    category_code: Annotated[str, Field(min_length=1, max_length=32)]
    is_leaf: bool = False
    sort_order: int = 0
    remark: Annotated[str | None, Field(default=None, max_length=500)] = None

    @field_validator("category_name", "category_code", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)

    @field_validator("product_kind", "category_code", mode="before")
    @classmethod
    def _upper_text(cls, v: object) -> object:
        return _upper(v)


class PmsCategoryUpdate(_Base):
    category_name: Annotated[str | None, Field(default=None, max_length=128)] = None
    category_code: Annotated[str | None, Field(default=None, max_length=32)] = None
    is_leaf: bool | None = None
    sort_order: int | None = None
    remark: Annotated[str | None, Field(default=None, max_length=500)] = None

    @field_validator("category_name", "category_code", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)

    @field_validator("category_code", mode="before")
    @classmethod
    def _upper_code(cls, v: object) -> object:
        return _upper(v)


class PmsCategoryOut(_Base):
    id: int
    parent_id: int | None
    level: int
    product_kind: str
    category_name: str
    category_code: str
    path_code: str
    is_leaf: bool
    is_active: bool
    is_locked: bool
    sort_order: int
    remark: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ItemAttributeDefCreate(_Base):
    code: Annotated[str, Field(min_length=1, max_length=64)]
    name_cn: Annotated[str, Field(min_length=1, max_length=128)]
    name_en: Annotated[str | None, Field(default=None, max_length=128)] = None
    product_kind: AttributeProductKind
    category_id: int | None = None
    value_type: AttributeValueType
    unit: Annotated[str | None, Field(default=None, max_length=16)] = None
    is_required: bool = False
    is_searchable: bool = False
    is_filterable: bool = False
    is_sku_segment: bool = False
    sort_order: int = 0
    remark: Annotated[str | None, Field(default=None, max_length=500)] = None

    @field_validator("code", "name_cn", "name_en", "unit", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)

    @field_validator("code", "product_kind", "value_type", mode="before")
    @classmethod
    def _upper_text(cls, v: object) -> object:
        return _upper(v)


class ItemAttributeDefUpdate(_Base):
    name_cn: Annotated[str | None, Field(default=None, max_length=128)] = None
    name_en: Annotated[str | None, Field(default=None, max_length=128)] = None
    unit: Annotated[str | None, Field(default=None, max_length=16)] = None
    is_required: bool | None = None
    is_searchable: bool | None = None
    is_filterable: bool | None = None
    is_sku_segment: bool | None = None
    sort_order: int | None = None
    remark: Annotated[str | None, Field(default=None, max_length=500)] = None

    @field_validator("name_cn", "name_en", "unit", "remark", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)


class ItemAttributeDefOut(_Base):
    id: int
    code: str
    name_cn: str
    name_en: str | None = None
    product_kind: str
    category_id: int | None = None
    value_type: str
    unit: str | None = None
    is_required: bool
    is_searchable: bool
    is_filterable: bool
    is_sku_segment: bool
    is_active: bool
    sort_order: int
    remark: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ItemAttributeOptionCreate(_Base):
    option_code: Annotated[str, Field(min_length=1, max_length=64)]
    option_name: Annotated[str, Field(min_length=1, max_length=128)]
    sort_order: int = 0

    @field_validator("option_code", "option_name", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)

    @field_validator("option_code", mode="before")
    @classmethod
    def _upper_code(cls, v: object) -> object:
        return _upper(v)


class ItemAttributeOptionUpdate(_Base):
    option_name: Annotated[str | None, Field(default=None, max_length=128)] = None
    sort_order: int | None = None

    @field_validator("option_name", mode="before")
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _trim(v)


class ItemAttributeOptionOut(_Base):
    id: int
    attribute_def_id: int
    option_code: str
    option_name: str
    is_active: bool
    sort_order: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ItemAttributeValueIn(_Base):
    attribute_def_id: Annotated[int, Field(ge=1)]
    value_text: str | None = None
    value_number: Decimal | None = None
    value_bool: bool | None = None
    value_option_id: int | None = None

    @model_validator(mode="after")
    def _one_value(self) -> "ItemAttributeValueIn":
        filled = [
            self.value_text is not None and str(self.value_text).strip() != "",
            self.value_number is not None,
            self.value_bool is not None,
            self.value_option_id is not None,
        ]
        if sum(1 for x in filled if x) > 1:
            raise ValueError("每个属性值只能提交一种 value_*")
        return self


class ItemAttributeValueOut(_Base):
    id: int
    item_id: int
    attribute_def_id: int
    value_text: str | None = None
    value_number: Decimal | None = None
    value_bool: bool | None = None
    value_option_id: int | None = None
    value_option_code_snapshot: str | None = None
    value_unit_snapshot: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ItemAttributeValuesReplaceIn(_Base):
    values: list[ItemAttributeValueIn] = Field(default_factory=list)


class ListOut[T](_Base):
    ok: bool = True
    data: list[T]
