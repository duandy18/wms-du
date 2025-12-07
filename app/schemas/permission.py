# app/schemas/permission.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段（对旧客户端更宽容）
    - populate_by_name: 支持别名/字段名互填（便于未来加 alias）
    """

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 创建 / 更新 =========
class PermissionCreate(_Base):
    """
    新建权限
    - name 建议形如：`stock.read` / `order.approve`
    """

    name: Annotated[str, Field(min_length=1, max_length=64, description="权限名（唯一）")]
    description: Annotated[str | None, Field(default=None, max_length=256)] = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"name": "stock.read", "description": "读取库存数据"}}
    }


class PermissionUpdate(_Base):
    """
    更新权限（至少提供一项）
    """

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=64)] = None
    description: Annotated[str | None, Field(default=None, max_length=256)] = None

    @field_validator("*", mode="after")
    @classmethod
    def _at_least_one(cls, _v, info):
        data = info.data
        if all(v is None for v in data.values()):
            raise ValueError("至少提供一个要更新的字段")
        return _v

    @field_validator("name", "description", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"description": "允许审批订单"}}
    }


# ========= 输出 =========
class PermissionOut(_Base):
    # 关键修复：id 改为 int，与 DB 中 permissions.id 对齐
    id: Annotated[int, Field(description="权限ID（整数）")]
    name: Annotated[str, Field(min_length=1, max_length=64)]
    description: Annotated[str | None, Field(default=None, max_length=256)] = None

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"id": 1, "name": "stock.read", "description": "读取库存数据"}
        }
    }


__all__ = ["PermissionCreate", "PermissionUpdate", "PermissionOut"]
