# app/schemas/batch.py
from __future__ import annotations

from datetime import datetime
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


# ========= 基础字段 =========
class BatchBase(_Base):
    """
    批次基础字段（保持现有字段命名）
    """
    batch_number: Annotated[str, Field(min_length=1, max_length=100, description="批次编码")]
    production_date: datetime | None = Field(default=None, description="生产时间（可选）")
    expiration_date: datetime | None = Field(default=None, description="到期时间（可选）")

    @field_validator("batch_number", mode="before")
    @classmethod
    def _trim_batch_number(cls, v: str) -> str:
        return v.strip()

    @field_validator("expiration_date")
    @classmethod
    def _expiry_gte_production(cls, v: datetime | None, info):
        p: datetime | None = info.data.get("production_date")
        if v is not None and p is not None and v < p:
            raise ValueError("expiration_date 必须大于等于 production_date")
        return v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "batch_number": "B-20251028-A",
                "production_date": "2025-10-01T00:00:00Z",
                "expiration_date": "2026-04-01T00:00:00Z",
            }
        }
    }


# ========= 创建 =========
class BatchCreate(BatchBase):
    """创建批次"""
    pass


# ========= 更新（全部可选；至少一项必须提供） =========
class BatchUpdate(_Base):
    """
    更新批次信息：字段均为可选；至少提供一项
    """
    batch_number: Annotated[str | None, Field(default=None, min_length=1, max_length=100)] = None
    production_date: datetime | None = None
    expiration_date: datetime | None = None

    @field_validator("*", mode="after")
    @classmethod
    def _at_least_one(cls, _v, info):
        data = info.data
        if all(v is None for v in data.values()):
            raise ValueError("至少提供一个要更新的字段")
        return _v

    @field_validator("batch_number", mode="before")
    @classmethod
    def _trim_batch_number(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("expiration_date")
    @classmethod
    def _expiry_gte_production(cls, v: datetime | None, info):
        p: datetime | None = info.data.get("production_date")
        if v is not None and p is not None and v < p:
            raise ValueError("expiration_date 必须大于等于 production_date")
        return v

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "batch_number": "B-20251028-B",
                "expiration_date": "2026-06-01T00:00:00Z",
            }
        }
    }


# ========= 输出 =========
class BatchOut(BatchBase):
    id: Annotated[str, Field(description="批次ID（字符串，保持兼容）")]

    model_config = _Base.model_config | {
        "json_schema_extra": {
            "example": {
                "id": "batch_10001",
                "batch_number": "B-20251028-A",
                "production_date": "2025-10-01T00:00:00Z",
                "expiration_date": "2026-04-01T00:00:00Z",
            }
        }
    }


__all__ = ["BatchBase", "BatchCreate", "BatchUpdate", "BatchOut"]
