# app/api/routers/shipping_provider_pricing_schemes/schemas/dest_adjustment.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DestAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    scope: str
    province: str
    city: Optional[str] = None
    amount: float
    active: bool
    priority: int
    created_at: datetime
    updated_at: datetime


class DestAdjustmentUpsertIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope: str = Field(..., description="province|city")
    province: str
    city: Optional[str] = None
    amount: float
    active: bool = True
    priority: int = 100

    @field_validator("scope")
    @classmethod
    def _scope(cls, v: str) -> str:
        v2 = (v or "").strip().lower()
        if v2 not in ("province", "city"):
            raise ValueError("scope must be 'province' or 'city'")
        return v2

    @field_validator("province")
    @classmethod
    def _province(cls, v: str) -> str:
        v2 = (v or "").strip()
        if not v2:
            raise ValueError("province is required")
        return v2

    @field_validator("city")
    @classmethod
    def _city(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        return v2 or None


class DestAdjustmentUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    amount: Optional[float] = None
    active: Optional[bool] = None
    priority: Optional[int] = None

    @field_validator("scope")
    @classmethod
    def _scope(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip().lower()
        if v2 not in ("province", "city"):
            raise ValueError("scope must be 'province' or 'city'")
        return v2

    @field_validator("province")
    @classmethod
    def _province(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        if not v2:
            raise ValueError("province is required")
        return v2

    @field_validator("city")
    @classmethod
    def _city(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v2 = v.strip()
        return v2 or None
