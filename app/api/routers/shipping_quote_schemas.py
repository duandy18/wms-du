# app/api/routers/shipping_quote_schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QuoteDestIn(BaseModel):
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None

    province_code: str = Field(..., min_length=1)
    city_code: Optional[str] = Field(default=None, min_length=1)


class QuoteSnapshotSelectedQuote(BaseModel):
    quote_status: str = Field(default="OK")
    scheme_id: Optional[int] = None
    scheme_name: Optional[str] = None
    provider_id: Optional[int] = None
    carrier_code: Optional[str] = None
    carrier_name: Optional[str] = None
    currency: Optional[str] = None
    total_amount: float

    weight: Dict[str, Any] = Field(default_factory=dict)
    destination_group: Optional[Dict[str, Any]] = None
    pricing_matrix: Optional[Dict[str, Any]] = None
    breakdown: Dict[str, Any] = Field(default_factory=dict)
    reasons: List[str] = Field(default_factory=list, min_length=1)


class QuoteSnapshot(BaseModel):
    version: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    input: Dict[str, Any] = Field(default_factory=dict)
    selected_quote: QuoteSnapshotSelectedQuote


class QuoteCalcIn(BaseModel):
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
    destination_group: Optional[Dict[str, Any]] = None
    pricing_matrix: Optional[Dict[str, Any]] = None

    breakdown: Dict[str, Any]
    reasons: List[str] = Field(default_factory=list)

    quote_snapshot: Optional[QuoteSnapshot] = None


class QuoteRecommendIn(BaseModel):
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
    destination_group: Optional[Dict[str, Any]] = None
    pricing_matrix: Optional[Dict[str, Any]] = None
    breakdown: Dict[str, Any]
    reasons: List[str] = Field(default_factory=list)

    quote_snapshot: Optional[QuoteSnapshot] = None


class QuoteRecommendOut(BaseModel):
    ok: bool
    recommended_scheme_id: Optional[int] = None
    quotes: List[QuoteRecommendItemOut]
