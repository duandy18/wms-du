# app/schemas/inventory.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MovementType


class _Base(BaseModel):
    """
    终态 schema 基类：
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段（兼容旧客户端额外字段，但不再接受 legacy_location）
    - populate_by_name: 支持别名/字段名互填
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


class InventoryMovementCreate(_Base):
    """
    创建一条库存移动记录（终态：warehouse 维度）。

    - legacy_location 维度已彻底移除，不再兼容。
    """

    item_sku: Annotated[str, Field(min_length=1, max_length=128)]
    warehouse_id: Annotated[int, Field(gt=0, description="仓库 ID（>0）")]
    quantity: Annotated[float, Field(gt=0)]
    movement_type: MovementType

    @field_validator("item_sku", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "item_sku": "CAT-FOOD-15KG",
                "warehouse_id": 1,
                "quantity": 10,
                "movement_type": "RECEIPT",
            }
        }
    }


class InventoryMovementOut(InventoryMovementCreate):
    """
    库存移动记录（只读输出）
    """

    id: str
    timestamp: datetime


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


__all__ = ["InventoryMovementCreate", "InventoryMovementOut", "StockOnHandOut"]
