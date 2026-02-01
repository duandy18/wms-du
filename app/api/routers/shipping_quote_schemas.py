# app/api/routers/shipping_quote_schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QuoteDestIn(BaseModel):
    # ✅ 兼容期展示字段（允许只传 name）
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    # ✅ 事实字段：GB2260 code（主线真相）
    # - province_code：强制必填（护栏 B）
    # - city_code：可选（直辖市可由前端/后端推导；普通省份若有 city 规则则建议传）
    province_code: str = Field(..., min_length=1)
    city_code: Optional[str] = Field(default=None, min_length=1)


class QuoteCalcIn(BaseModel):
    # ✅ Phase 4.x：强前置起运仓（无 warehouse_id 直接拒绝）
    warehouse_id: int = Field(..., ge=1)

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
    """
    Phase 3/4 严格合同（无兼容）：
    - warehouse_id 必填：推荐必须发生在“起运仓边界”内
    - provider_ids 仅作为“过滤交集”，不允许绕过仓库边界（即不允许 warehouse_id 缺失）
    """
    warehouse_id: int = Field(..., ge=1)

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
