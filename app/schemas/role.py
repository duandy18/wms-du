# app/schemas/role.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 前向引用，避免循环导入
from .permission import PermissionOut


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
class RoleCreate(_Base):
    name: Annotated[str, Field(min_length=1, max_length=64, description="角色名称")]
    description: Annotated[str | None, Field(default=None, max_length=256)] = None

    @field_validator("name", "description", mode="before")
    @classmethod
    def _trim_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {"name": "warehouse.admin", "description": "仓库管理员，可管理库存与订单"}
        }
    }


class RoleUpdate(_Base):
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
        "json_schema_extra": {"example": {"description": "仅限出库审批权限"}}
    }


# ========= 输出 =========
class RoleOut(_Base):
    # **关键修复：id 从 str → int，与 DB 对齐**
    id: Annotated[int, Field(description="角色ID（整数）")]

    name: Annotated[str, Field(min_length=1, max_length=64)]
    description: Annotated[str | None, Field(default=None, max_length=256)] = None

    # 修复可变默认值：使用 default_factory
    permissions: list[PermissionOut] = Field(default_factory=list)

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "id": 1,
                "name": "warehouse.admin",
                "description": "仓库管理员，可管理库存与订单",
                "permissions": [
                    {
                        "id": 1,
                        "name": "stock.read",
                        "description": "读取库存",
                        "scope": "stock",
                    },
                    {
                        "id": 2,
                        "name": "order.approve",
                        "description": "订单审批",
                        "scope": "order",
                    },
                ],
            }
        }
    }


__all__ = ["RoleCreate", "RoleUpdate", "RoleOut"]
