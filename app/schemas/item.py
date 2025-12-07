# app/schemas/item.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ========= 通用基类 =========
class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 基础字段（含保质期 + 重量） =========
class ItemBase(_Base):
    sku: Annotated[str, Field(min_length=1, max_length=128)]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool = True
    supplier_id: Annotated[int | None, Field(default=None)] = None

    # 新增：保质期结构
    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[
        Literal["DAY", "MONTH"] | None,
        Field(default=None),
    ] = None

    # ⭐ 新增：单件净重（kg），用于运费预估
    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator("sku", "name", "spec", "uom", "barcode", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v


# ========= 创建 =========
class ItemCreate(ItemBase):
    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "sku": "CAT-FOOD-15KG",
                "name": "顽皮双拼猫粮 1.5kg",
                "spec": "鸡肉+牛肉",
                "uom": "bag",
                "barcode": "6901234567890",
                "enabled": True,
                "supplier_id": 1,
                "shelf_life_value": 18,
                "shelf_life_unit": "MONTH",
                "weight_kg": 1.5,
            }
        }
    }


# ========= 更新 =========
class ItemUpdate(_Base):
    sku: Annotated[str | None, Field(default=None, max_length=128)] = None
    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None

    enabled: bool | None = None
    supplier_id: int | None = None

    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[
        Literal["DAY", "MONTH"] | None,
        Field(default=None),
    ] = None

    # ⭐ 新增：更新时允许修改重量
    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None

    @field_validator("sku", "name", "spec", "uom", "barcode", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _at_least_one(self):
        if all(
            getattr(self, f) is None
            for f in (
                "sku",
                "name",
                "spec",
                "uom",
                "barcode",
                "enabled",
                "supplier_id",
                "shelf_life_value",
                "shelf_life_unit",
                "weight_kg",
            )
        ):
            raise ValueError("至少提供一个更新字段")
        return self


# ========= 按 ID 创建 =========
class ItemCreateById(_Base):
    id: Annotated[int, Field(gt=0)]
    sku: Annotated[str | None, Field(default=None, max_length=128)] = None
    name: Annotated[str | None, Field(default=None, max_length=128)] = None
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None
    enabled: bool | None = True
    supplier_id: int | None = None

    shelf_life_value: Annotated[int | None, Field(default=None, ge=0)] = None
    shelf_life_unit: Annotated[
        Literal["DAY", "MONTH"] | None,
        Field(default=None),
    ] = None

    # ⭐ 按 ID 创建时也可带上 weight_kg
    weight_kg: Annotated[float | None, Field(default=None, ge=0)] = None


# ========= 输出 =========
class ItemOut(ItemBase):
    id: int
    supplier_name: str | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = [
    "ItemBase",
    "ItemCreate",
    "ItemUpdate",
    "ItemCreateById",
    "ItemOut",
]
