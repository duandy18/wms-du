# app/schemas/inventory.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    """
    终态 schema 基类：
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段
    - populate_by_name: 支持别名/字段名互填
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class StockOnHandOut(_Base):
    """
    库存现存量（终态：按 SKU + warehouse 汇总）。
    """

    item_sku: Annotated[str, Field(min_length=1, max_length=128)]
    warehouse_id: Annotated[int, Field(gt=0)]
    quantity: Annotated[float, Field(ge=0)]

    @field_validator("item_sku", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v


__all__ = ["StockOnHandOut"]
