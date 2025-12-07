# app/schemas/auth.py
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ===== 常量（对齐原文件风格） =====
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 32
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


# ===== 统一基类：允许 ORM / 忽略冗余字段 / 兼容别名填充 =====
class _Base(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ===== 注册 =====
class RegisterIn(_Base):
    """
    用户注册入参
    """

    username: Annotated[str, Field(min_length=MIN_USERNAME_LENGTH, max_length=MAX_USERNAME_LENGTH)]
    email: EmailStr
    password: Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]

    @field_validator("username", mode="before")
    @classmethod
    def _trim_username(cls, v: str) -> str:
        v = v.strip()
        if not (MIN_USERNAME_LENGTH <= len(v) <= MAX_USERNAME_LENGTH):
            raise ValueError(f"username length must be {MIN_USERNAME_LENGTH}-{MAX_USERNAME_LENGTH}")
        return v

    @field_validator("password", mode="before")
    @classmethod
    def _trim_password(cls, v: str) -> str:
        v = v.strip()
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
        return v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "username": "duandy",
                "email": "duandy@example.com",
                "password": "Str0ngPass!",
            }
        }
    }


# ===== 登录 =====
class LoginIn(_Base):
    """
    用户登录入参（username 或 email 至少提供其一）
    """

    username: str | None = None
    email: EmailStr | None = None
    password: Annotated[str, Field(min_length=1)]

    @field_validator("username", mode="before")
    @classmethod
    def _trim_username(cls, v: str | None) -> str | None:
        return v.strip() if isinstance(v, str) else v

    @field_validator("username", mode="after")
    @classmethod
    def _require_username_or_email(cls, v: str | None, info) -> str | None:
        email = info.data.get("email")
        if v is None and email is None:
            raise ValueError("Must provide either username or email.")
        return v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "username": "duandy",
                "password": "Str0ngPass!",
                # 或者使用 email 登录：
                # "email": "duandy@example.com",
            }
        }
    }


# ===== 令牌（输出） =====
class TokenOut(_Base):
    """
    JWT 令牌输出
    """

    access_token: str
    token_type: Annotated[str, Field(default="bearer")] = "bearer"

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }
        }
    }


# ===== 令牌内载荷（只读/内部使用） =====
class TokenData(_Base):
    """
    JWT payload 常见字段
    - sub: 一般放用户 ID
    - username: 用户名（可选）
    - is_admin: 是否管理员（可选）
    """

    sub: str | None = None
    username: str | None = None
    is_admin: bool | None = False

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "sub": "user:1",
                "username": "duandy",
                "is_admin": False,
            }
        }
    }


__all__ = ["RegisterIn", "LoginIn", "TokenOut", "TokenData"]
