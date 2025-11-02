# app/schemas/item.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段，兼容旧客户端
    - populate_by_name: 支持别名/字段名互填（便于未来加 alias）
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 基础字段 =========
class ItemBase(_Base):
    """
    商品基础字段
    """
    sku: Annotated[str, Field(min_length=1, max_length=128, description="商品SKU")]
    name: Annotated[str, Field(min_length=1, max_length=128, description="商品名称")]
    spec: Annotated[str | None, Field(default=None, max_length=128, description="规格/口味等（可选）")] = None
    uom: Annotated[str | None, Field(default=None, max_length=32, description="计量单位（可选）")] = None
    barcode: Annotated[str | None, Field(default=None, max_length=64, description="条码（可选）")] = None
    enabled: bool = True

    @field_validator("sku", "name", "spec", "uom", "barcode", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v


# ========= 创建 / 更新 =========
class ItemCreate(ItemBase):
    """
    创建商品
    """
    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "sku": "CAT-FOOD-15KG",
                "name": "顽皮双拼猫粮 1.5kg",
                "spec": "鸡肉+牛肉",
                "uom": "bag",
                "barcode": "6901234567890",
                "enabled": True,
            }
        }
    }


class ItemUpdate(_Base):
    """
    更新商品：字段均为可选；至少提供一项
    """
    sku: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    spec: Annotated[str | None, Field(default=None, max_length=128)] = None
    uom: Annotated[str | None, Field(default=None, max_length=32)] = None
    barcode: Annotated[str | None, Field(default=None, max_length=64)] = None
    enabled: bool | None = None

    @field_validator("*", mode="after")
    @classmethod
    def _at_least_one(cls, _v, info):
        data = info.data
        if all(v is None for v in data.values()):
            raise ValueError("至少提供一个要更新的字段")
        return _v

    @field_validator("sku", "name", "spec", "uom", "barcode", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "name": "顽皮双拼猫粮 1.5kg（新包装）",
                "barcode": "6901234567891",
            }
        }
    }


# ========= 输出（只读） =========
class ItemOut(ItemBase):
    id: int
    created_at: str | None = None
    updated_at: str | None = None

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "id": 777,
                "sku": "CAT-FOOD-15KG",
                "name": "顽皮双拼猫粮 1.5kg",
                "spec": "鸡肉+牛肉",
                "uom": "bag",
                "barcode": "6901234567890",
                "enabled": True,
                "created_at": "2025-10-28T09:00:00Z",
                "updated_at": "2025-10-28T09:30:00Z",
            }
        }
    }


# ========= 兼容保留：你原文件中的库存调整模型 =========
# 说明：这两个模型更适合放在 stock.py 中；出于兼容性考虑继续在此导出。
class StockAdjIn(_Base):
    """兼容保留：库存调整入参（建议迁移到 app/schemas/stock.py）"""
    item_id: int
    delta: int
    reason: str | None = None

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"item_id": 777, "delta": -2, "reason": "DAMAGED"}
        }
    }


class StockAdjOut(_Base):
    """兼容保留：库存调整结果（建议迁移到 app/schemas/stock.py）"""
    item_id: int
    qty_available: int

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"item_id": 777, "qty_available": 128}
        }
    }


__all__ = [
    "ItemBase",
    "ItemCreate",
    "ItemUpdate",
    "ItemOut",
    # 兼容保留
    "StockAdjIn",
    "StockAdjOut",
]
