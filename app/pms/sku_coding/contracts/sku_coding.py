# app/pms/sku_coding/contracts/sku_coding.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProductKind = Literal["FOOD", "SUPPLY"]
TermProductKind = Literal["FOOD", "SUPPLY", "COMMON"]


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


def _trim(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class SkuCodeTermGroupOut(_Base):
    id: int
    product_kind: str
    group_code: str
    group_name: str
    is_multi_select: bool
    is_required: bool
    sort_order: int
    is_active: bool
    remark: str | None


class SkuCodeTermCreate(_Base):
    group_id: Annotated[int, Field(ge=1)]
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
    def _upper_text(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v


class SkuCodeTermUpdate(_Base):
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
    def _upper_text(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v


class SkuCodeTermOut(_Base):
    id: int
    group_id: int
    name_cn: str
    code: str
    sort_order: int
    is_active: bool
    is_locked: bool
    remark: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SkuGenerateIn(_Base):
    product_kind: ProductKind
    brand_id: Annotated[int, Field(ge=1)]
    category_id: Annotated[int, Field(ge=1)]
    term_ids: dict[str, list[int]] = Field(default_factory=dict)
    text_segments: dict[str, str] = Field(default_factory=dict)
    spec_text: Annotated[str, Field(min_length=1, max_length=64)]

    @field_validator("product_kind", mode="before")
    @classmethod
    def _upper_kind(cls, v: object) -> object:
        return v.strip().upper() if isinstance(v, str) else v

    @field_validator("spec_text", mode="before")
    @classmethod
    def _trim_spec(cls, v: object) -> object:
        return _trim(v)


class SkuGeneratedSegmentOut(_Base):
    segment_key: str
    name_cn: str
    code: str


class SimilarItemOut(_Base):
    id: int
    sku: str
    name: str
    spec: str | None
    brand_id: int | None = None
    category_id: int | None = None
    brand: str | None
    category: str | None


class SkuGenerateDataOut(_Base):
    sku: str
    segments: list[SkuGeneratedSegmentOut]
    exists: bool
    similar_items: list[SimilarItemOut]


class SkuGenerateOut(_Base):
    ok: bool = True
    data: SkuGenerateDataOut


class ListOut[T](_Base):
    ok: bool = True
    data: list[T]
