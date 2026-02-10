# app/api/routers/platform_orders_manual_decisions_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr


class ManualDecisionLineOut(BaseModel):
    """
    人工救火明细行（证据表读侧输出）。

    Phase N+4：line_key（内部幂等锚点）与 locator（对外定位语义）分层。
    """

    model_config = ConfigDict(extra="ignore")

    # internal / legacy (kept for compatibility)
    line_key: Optional[str] = None
    line_no: Optional[int] = None

    # semantic locator (recommended)
    locator_kind: Optional[str] = Field(
        default=None,
        description="对外定位类型（推荐）：FILLED_CODE / LINE_NO",
    )
    locator_value: Optional[str] = Field(
        default=None,
        description="对外定位值（推荐）",
    )

    filled_code: Optional[str] = Field(
        default=None,
        description="商家后台填写码（对外语义字段）",
    )

    fact_qty: Optional[int] = None
    item_id: Optional[int] = None
    qty: Optional[int] = None
    note: Optional[str] = None


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
    manual_decisions: List[ManualDecisionLineOut] = Field(default_factory=list)


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
