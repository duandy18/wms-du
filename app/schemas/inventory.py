# app/schemas/inventory.py
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 统一：使用项目内集中定义的业务枚举
from app.models.enums import MovementType


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段，兼容旧客户端
    - populate_by_name: 支持别名/字段名互填（便于未来演进）
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 库存移动（创建 / 输出） =========
class InventoryMovementCreate(_Base):
    """
    创建一条库存移动记录（入库/出库/转移/调整）。
    - item_sku: 商品 SKU（字符串）
    - from_location_id/to_location_id: 库位 ID（字符串，可空；入库/出库时通常有一端为空）
    - quantity: 变动数量（正数；具体方向由 movement_type 决定）
    - movement_type: RECEIPT/SHIPMENT/TRANSFER/ADJUSTMENT
    """
    item_sku: Annotated[str, Field(min_length=1, max_length=128)]
    from_location_id: str | None = None
    to_location_id: str | None = None
    quantity: Annotated[float, Field(gt=0)]
    movement_type: MovementType

    @field_validator("item_sku", "from_location_id", "to_location_id", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "item_sku": "CAT-FOOD-15KG",
                "from_location_id": None,
                "to_location_id": "LOC-RECEIVE-01",
                "quantity": 10,
                "movement_type": "receipt",
            }
        }
    }


class InventoryMovementOut(InventoryMovementCreate):
    """
    库存移动记录（只读输出）
    """
    id: str
    timestamp: datetime

    # 继承 _Base 的 v2 配置
    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "id": "mv_20251028_0001",
                "item_sku": "CAT-FOOD-15KG",
                "from_location_id": None,
                "to_location_id": "LOC-RECEIVE-01",
                "quantity": 10,
                "movement_type": "receipt",
                "timestamp": "2025-10-28T10:20:00Z",
            }
        }
    }


# ========= 现存量（只读） =========
class StockOnHandOut(_Base):
    """
    库存现存量（按 SKU + 库位汇总）
    """
    item_sku: Annotated[str, Field(min_length=1, max_length=128)]
    location_id: Annotated[str, Field(min_length=1, max_length=128)]
    quantity: Annotated[float, Field(ge=0)]

    @field_validator("item_sku", "location_id", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "item_sku": "CAT-FOOD-15KG",
                "location_id": "LOC-RECEIVE-01",
                "quantity": 128.0,
            }
        }
    }


__all__ = ["InventoryMovementCreate", "InventoryMovementOut", "StockOnHandOut"]
