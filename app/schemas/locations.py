# app/schemas/locations.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段（对旧客户端更宽容）
    - populate_by_name: 支持别名/字段名互填（便于未来演进）
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 仓库（Warehouse） =========
class WarehouseCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128, description="仓库名称")]
    address: Annotated[
        str | None, Field(default=None, max_length=256, description="地址（可选）")
    ] = None

    @field_validator("name", "address", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"name": "上海一号仓", "address": "浦东新区川沙路 123 号"}}
    }


class WarehouseUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    address: Annotated[str | None, Field(default=None, max_length=256)] = None

    @field_validator("*", mode="after")
    @classmethod
    def _at_least_one(cls, _v, info):
        data = info.data
        if all(v is None for v in data.values()):
            raise ValueError("至少提供一个要更新的字段")
        return _v

    @field_validator("name", "address", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"address": "宝山区呼兰路 456 号"}}
    }


class WarehouseOut(_Base):
    id: Annotated[str, Field(description="仓库ID（保持字符串以兼容现有接口）")]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    address: Annotated[str | None, Field(default=None, max_length=256)] = None

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"id": "wh_01", "name": "上海一号仓", "address": "浦东新区川沙路 123 号"}
        }
    }


# ========= 库位（Location） =========
class LocationCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128, description="库位名称/编码")]
    warehouse_id: Annotated[
        str, Field(min_length=1, max_length=64, description="所属仓库ID（字符串）")
    ]

    @field_validator("name", "warehouse_id", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"name": "A-01-01", "warehouse_id": "wh_01"}}
    }


class LocationUpdate(_Base):
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    warehouse_id: Annotated[str | None, Field(default=None, min_length=1, max_length=64)] = None

    @field_validator("*", mode="after")
    @classmethod
    def _at_least_one(cls, _v, info):
        data = info.data
        if all(v is None for v in data.values()):
            raise ValueError("至少提供一个要更新的字段")
        return _v

    @field_validator("name", "warehouse_id", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {"json_schema_extra": {"example": {"name": "A-01-02"}}}


class LocationOut(_Base):
    id: Annotated[str, Field(description="库位ID（保持字符串以兼容现有接口）")]
    name: Annotated[str, Field(min_length=1, max_length=128)]
    warehouse_id: Annotated[str, Field(min_length=1, max_length=64)]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"id": "loc_1001", "name": "A-01-01", "warehouse_id": "wh_01"}
        }
    }


__all__ = [
    "WarehouseCreate",
    "WarehouseUpdate",
    "WarehouseOut",
    "LocationCreate",
    "LocationUpdate",
    "LocationOut",
]
