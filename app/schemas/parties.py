# app/schemas/parties.py
from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# 复用你现有的业务枚举/模型出口
from app.models.parties import PartyType


# ========= 通用基类（v1.0 统一） =========
class _Base(BaseModel):
    """
    - from_attributes: 允许 ORM 对象直接转出
    - extra="ignore": 忽略冗余字段，兼容旧客户端
    - populate_by_name: 支持别名/字段名互填
    """
    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
        populate_by_name=True,
    )


# ========= 基础字段 =========
class PartyBase(_Base):
    name: Annotated[str, Field(min_length=1, max_length=128, description="伙伴名称")]
    party_type: PartyType
    contact_person: Annotated[str | None, Field(default=None, max_length=64)] = None
    phone_number: Annotated[str | None, Field(default=None, max_length=32)] = None
    email: EmailStr | None = None
    address: Annotated[str | None, Field(default=None, max_length=256)] = None

    @field_validator("name", "contact_person", "address", mode="before")
    @classmethod
    def _trim_text(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("phone_number")
    @classmethod
    def _check_phone(cls, v: str | None):
        # 轻量校验：仅允许数字、空格、+、-、() 这些常见字符
        if v is None:
            return v
        if not re.fullmatch(r"[0-9+\-\s()]{5,32}", v.strip()):
            raise ValueError("phone_number 格式不合法")
        return v


# ========= 创建 / 更新 =========
class PartyCreate(PartyBase):
    """
    创建伙伴（供应商/客户/承运商等）
    """
    pass


class PartyUpdate(_Base):
    """
    更新伙伴信息：字段均为可选；至少提供一项
    """
    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    party_type: PartyType | None = None
    contact_person: Annotated[str | None, Field(default=None, max_length=64)] = None
    phone_number: Annotated[str | None, Field(default=None, max_length=32)] = None
    email: EmailStr | None = None
    address: Annotated[str | None, Field(default=None, max_length=256)] = None

    @field_validator("*", mode="after")
    @classmethod
    def _at_least_one(cls, _v, info):
        # 除 None 外至少有一项被设置
        data = info.data
        if all(v is None for v in data.values()):
            raise ValueError("至少提供一个要更新的字段")
        return _v

    @field_validator("name", "contact_person", "address", mode="before")
    @classmethod
    def _trim_text(cls, v):
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator("phone_number")
    @classmethod
    def _check_phone(cls, v: str | None):
        if v is None:
            return v
        if not re.fullmatch(r"[0-9+\-\s()]{5,32}", v.strip()):
            raise ValueError("phone_number 格式不合法")
        return v


# ========= 输出（只读） =========
class PartyOut(PartyBase):
    id: str  # 保持与现有接口一致，不更改为 int，避免破坏兼容
    model_config = _Base.model_config


__all__ = ["PartyBase", "PartyCreate", "PartyUpdate", "PartyOut"]
