# app/api/routers/shipping_provider_pricing_schemes/schemas/surcharge.py
from __future__ import annotations

from typing import Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


JsonObject = Dict[str, object]


class SurchargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scheme_id: int
    name: str
    active: bool
    condition_json: JsonObject
    amount_json: JsonObject


class SurchargeCreateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., min_length=1, max_length=128)
    active: bool = True
    condition_json: JsonObject
    amount_json: JsonObject

    @field_validator("amount_json")
    @classmethod
    def _reject_deprecated_rounding(cls, v: JsonObject):
        # ✅ amount_json.rounding 已废弃且不再生效
        if isinstance(v, dict) and ("rounding" in v) and (v.get("rounding") is not None):
            raise ValueError("amount_json.rounding is deprecated and ignored; use scheme.billable_weight_rule.rounding")
        return v


class SurchargeUpdateIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    active: Optional[bool] = None
    condition_json: Optional[JsonObject] = None
    amount_json: Optional[JsonObject] = None

    @field_validator("amount_json")
    @classmethod
    def _reject_deprecated_rounding(cls, v: Optional[JsonObject]):
        # ✅ amount_json.rounding 已废弃且不再生效
        if v is None:
            return v
        if isinstance(v, dict) and ("rounding" in v) and (v.get("rounding") is not None):
            raise ValueError("amount_json.rounding is deprecated and ignored; use scheme.billable_weight_rule.rounding")
        return v


# ✅ 新主入口：省/市 + 金额 直接写后端事实（upsert）
class SurchargeUpsertIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scope: Literal["province", "city"]
    province: str = Field(..., min_length=1, max_length=64)
    city: Optional[str] = Field(None, min_length=1, max_length=64)

    # 可选：前端不传则后端自动生成
    name: Optional[str] = Field(None, min_length=1, max_length=128)

    amount: float = Field(..., ge=0.0)
    active: bool = True

    @field_validator("province")
    @classmethod
    def _trim_province(cls, v: str) -> str:
        vv = (v or "").strip()
        if not vv:
            raise ValueError("province is required")
        return vv

    @field_validator("city")
    @classmethod
    def _trim_city(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        vv = v.strip()
        return vv or None

    @field_validator("scope")
    @classmethod
    def _scope_ok(cls, v: str) -> str:
        vv = (v or "").strip().lower()
        if vv not in ("province", "city"):
            raise ValueError("scope must be province|city")
        return vv

    @field_validator("amount")
    @classmethod
    def _amount_ok(cls, v: float) -> float:
        # Field(ge=0) 已覆盖，但这里再保险避免 NaN
        if v is None:
            raise ValueError("amount is required")
        if not isinstance(v, (int, float)):
            raise ValueError("amount must be a number")
        if v != v:  # NaN
            raise ValueError("amount must be a number")
        if v < 0:
            raise ValueError("amount must be >= 0")
        return float(v)

    @field_validator("city")
    @classmethod
    def _city_required_if_scope_city(cls, v: Optional[str], info):
        scope = (info.data.get("scope") or "").strip().lower()
        if scope == "city" and not v:
            raise ValueError("city is required when scope=city")
        return v
