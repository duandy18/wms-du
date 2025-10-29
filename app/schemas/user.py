# app/schemas/user.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# 前向引用，避免循环导入
from .role import RoleOut


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


# ========= 基础字段 =========
class UserBase(_Base):
    full_name: Annotated[str | None, Field(default=None, max_length=128)] = None
    email: EmailStr
    is_active: bool | None = True
    is_superuser: bool | None = False

    @field_validator("full_name", mode="before")
    @classmethod
    def _trim_name(cls, v):
        return v.strip() if isinstance(v, str) else v


# ========= 创建 / 更新 =========
class UserCreate(UserBase):
    """
    创建用户
    """
    # 明确密码长度下限；保持与现有接口一致（仅 email + password 必填）
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("password", mode="before")
    @classmethod
    def _trim_pwd(cls, v: str) -> str:
        return v.strip()


class UserUpdate(UserBase):
    """
    更新用户：字段均为可选；至少提供一项
    """
    password: Annotated[str | None, Field(default=None, min_length=8, max_length=128)] = None

    @field_validator("*", mode="after")
    @classmethod
    def _at_least_one(cls, _v, info):
        data = info.data
        # 除 None 外至少有一项被设置
        if all(v is None for v in data.values()):
            raise ValueError("至少提供一个要更新的字段")
        return _v

    @field_validator("password", mode="before")
    @classmethod
    def _trim_pwd(cls, v):
        return v.strip() if isinstance(v, str) else v


# ========= 输出（只读） =========
class UserOut(UserBase):
    id: str
    # 修复可变默认：使用 default_factory
    roles: list[RoleOut] = Field(default_factory=list)

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "id": "user_01",
                "full_name": "仓库管理员",
                "email": "admin@example.com",
                "is_active": True,
                "is_superuser": False,
                "roles": [
                    {"id": "role_01", "name": "warehouse.admin", "description": "仓库管理员", "permissions": []}
                ],
            }
        }
    }


__all__ = ["UserBase", "UserCreate", "UserUpdate", "UserOut"]
