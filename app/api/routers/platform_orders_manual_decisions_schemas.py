# app/api/routers/platform_orders_manual_decisions_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr


class ManualDecisionOrderOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # batch 追溯信息
    batch_id: str = Field(..., description="治理事实批次 id（platform_order_manual_decisions.batch_id）")
    created_at: datetime = Field(..., description="该批次最新写入时间（MAX(created_at)）")

    order_id: int
    platform: str
    shop_id: str
    ext_order_no: str
    ref: str

    store_id: int

    manual_reason: Optional[str] = None
    risk_flags: List[str] = Field(default_factory=list)
    manual_decisions: List[Dict[str, Any]] = Field(default_factory=list)


class ManualDecisionOrdersOut(BaseModel):
    items: List[ManualDecisionOrderOut] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class ManualDecisionOrdersQuery(BaseModel):
    """
    查询最近的“人工救火批次”（platform_order_manual_decisions），用于治理证据回流（不写绑定）。
    """

    model_config = ConfigDict(extra="ignore")

    platform: constr(min_length=1, max_length=32)
    store_id: int = Field(..., ge=1)
    limit: int = Field(20, ge=1, le=200)
    offset: int = Field(0, ge=0)
