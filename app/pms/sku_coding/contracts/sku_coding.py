# app/pms/sku_coding/contracts/sku_coding.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProductKind = Literal["FOOD", "SUPPLY"]


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


def _trim(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class SkuGenerateIn(_Base):
    product_kind: ProductKind
    brand_id: Annotated[int, Field(ge=1)]
    category_id: Annotated[int, Field(ge=1)]
    attribute_option_ids: dict[str, list[int]] = Field(default_factory=dict)
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
