# app/tms/shipment/contracts_calc.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ShipQuoteOut(BaseModel):
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


class ShipCalcRequest(BaseModel):
    warehouse_id: int = Field(..., ge=1, description="发货仓库 ID（Phase 3 强前置事实）")

    weight_kg: float = Field(..., gt=0, description="包裹总重量（kg）")
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    debug_ref: Optional[str] = Field(None, description="调试用标记，不参与计算，仅写入日志/事件")


class ShipRecommendedOut(BaseModel):
    provider_id: int
    carrier_code: Optional[str] = None
    template_id: int
    est_cost: Optional[float] = None
    currency: Optional[str] = None


class ShipCalcResponse(BaseModel):
    ok: bool = True
    weight_kg: float
    dest: Optional[str] = None
    quotes: List[ShipQuoteOut]
    recommended: Optional[ShipRecommendedOut] = None
