# app/pms/public/items/contracts/item_basic.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


def _norm_text(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class ItemBasic(_Base):
    """
    PMS 对外最小商品读模型。

    说明：
    - 这是跨域 public read surface，不承载 owner 内部兼容输入语义
    - 只暴露其他模块稳定需要的最小读取字段
    """

    id: Annotated[int, Field(gt=0)]
    sku: Annotated[str, Field(min_length=1, max_length=64)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None

    enabled: bool = True
    supplier_id: int | None = None

    brand: Annotated[str | None, Field(default=None, max_length=64)] = None
    category: Annotated[str | None, Field(default=None, max_length=64)] = None

    primary_barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    @field_validator(
        "sku",
        "name",
        "spec",
        "brand",
        "category",
        "primary_barcode",
        mode="before",
    )
    @classmethod
    def _trim_text(cls, v: object) -> object:
        return _norm_text(v)
