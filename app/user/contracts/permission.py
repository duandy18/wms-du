# app/user/contracts/permission.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 对象直接序列化
    - extra="ignore": 忽略冗余字段（对旧客户端更宽容）
    - populate_by_name: 支持别名/字段名互填
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

    name: Annotated[str, Field(min_length=1, max_length=128, description="权限名（唯一）")]

    @field_validator("name", mode="before")
    @classmethod
    def _trim_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"name": "stock.read"}}
    }


class PermissionUpdate(_Base):
    """
    更新权限（至少提供一项）
    """

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None

    @field_validator("name", mode="before")
    @classmethod
    def _trim_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.name is None:
            raise ValueError("至少提供一个要更新的字段")
        return self

    model_config = _Base.model_config | {
        "json_schema_extra": {"example": {"name": "order.approve"}}
    }


# ========= 输出 =========
class PermissionOut(_Base):
    id: Annotated[int, Field(description="权限ID（整数）")]
    name: Annotated[str, Field(min_length=1, max_length=128)]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"id": 1, "name": "stock.read"}
        }
    }


__all__ = ["PermissionCreate", "PermissionUpdate", "PermissionOut"]
