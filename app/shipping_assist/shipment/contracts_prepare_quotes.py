# app/shipping_assist/shipment/contracts_prepare_quotes.py
# 分拆说明：
# - 本文件从 contracts_prepare.py 中拆出“发运准备-包裹报价”相关合同。
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ShipPrepareQuoteCandidateOut(BaseModel):
    provider_id: int
    carrier_code: Optional[str] = None
    carrier_name: str
    template_id: int
    template_name: Optional[str] = None
    quote_status: str
    currency: Optional[str] = None
    est_cost: Optional[float] = None
    reasons: List[str] = Field(default_factory=list)
    breakdown: Optional[Dict[str, Any]] = None
    eta: Optional[str] = None


class ShipPreparePackageQuoteOut(BaseModel):
    package_no: int
    warehouse_id: int
    weight_kg: float
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    quotes: List[ShipPrepareQuoteCandidateOut] = Field(default_factory=list)


class ShipPreparePackageQuoteResponse(BaseModel):
    ok: bool = True
    item: ShipPreparePackageQuoteOut


class ShipPreparePackageQuoteConfirmRequest(BaseModel):
    provider_id: int = Field(..., ge=1)


class ShipPreparePackageQuoteConfirmOut(BaseModel):
    package_no: int
    pricing_status: str
    selected_provider_id: int
    selected_quote_snapshot: Dict[str, Any]


class ShipPreparePackageQuoteConfirmResponse(BaseModel):
    ok: bool = True
    item: ShipPreparePackageQuoteConfirmOut
