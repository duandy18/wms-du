# app/api/routers/shipping_quote_schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QuoteDestIn(BaseModel):
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None


class QuoteCalcIn(BaseModel):
    scheme_id: int = Field(..., ge=1)
    dest: QuoteDestIn

    real_weight_kg: float = Field(..., ge=0)
    length_cm: Optional[float] = Field(None, ge=0)
    width_cm: Optional[float] = Field(None, ge=0)
    height_cm: Optional[float] = Field(None, ge=0)

    flags: List[str] = Field(default_factory=list)


class QuoteCalcOut(BaseModel):
    ok: bool
    quote_status: str
    currency: Optional[str] = None
    total_amount: Optional[float] = None

    weight: Dict[str, Any]
    zone: Optional[Dict[str, Any]] = None
    bracket: Optional[Dict[str, Any]] = None

    breakdown: Dict[str, Any]
    reasons: List[str] = Field(default_factory=list)


class QuoteRecommendIn(BaseModel):
    # Phase 2：仓库候选集入口（可选）
    # - 若 provider_ids 为空且提供 warehouse_id，则按仓库绑定的可用快递公司计算推荐
    warehouse_id: Optional[int] = Field(default=None, ge=1)

    provider_ids: List[int] = Field(default_factory=list)
    dest: QuoteDestIn

    real_weight_kg: float = Field(..., ge=0)
    length_cm: Optional[float] = Field(None, ge=0)
    width_cm: Optional[float] = Field(None, ge=0)
    height_cm: Optional[float] = Field(None, ge=0)

    flags: List[str] = Field(default_factory=list)
    max_results: int = Field(default=10, ge=1, le=50)


class QuoteRecommendItemOut(BaseModel):
    provider_id: int
    carrier_code: Optional[str] = None
    carrier_name: str

    scheme_id: int
    scheme_name: str

    total_amount: float
    currency: Optional[str] = None

    quote_status: str

    weight: Dict[str, Any]
    zone: Optional[Dict[str, Any]] = None
    bracket: Optional[Dict[str, Any]] = None
    breakdown: Dict[str, Any]
    reasons: List[str] = Field(default_factory=list)


class QuoteRecommendOut(BaseModel):
    ok: bool
    recommended_scheme_id: Optional[int] = None
    quotes: List[QuoteRecommendItemOut]
