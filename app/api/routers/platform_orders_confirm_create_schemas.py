# app/api/routers/platform_orders_confirm_create_schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr


class PlatformOrderManualDecisionIn(BaseModel):
    """
    人工决策（当单执行）：
    - 通过 line_key / line_no / platform_sku_id 锚定到事实行
    - 人工选择仓库商品 item_id（不写 binding）
    """

    model_config = ConfigDict(extra="ignore")

    line_key: Optional[str] = Field(None, description="事实行键：PSKU:<psku> 或 NO_PSKU:<line_no>")
    line_no: Optional[int] = Field(None, ge=1, description="事实行序号（platform_order_lines.line_no）")
    platform_sku_id: Optional[str] = Field(None, description="平台 SKU（PSKU）")

    item_id: int = Field(..., ge=1, description="仓库商品 item_id（人工确认选货）")
    qty: int = Field(default=1, ge=1, description="该 item 的数量（>=1）")
    note: Optional[str] = Field(None, description="人工备注（可选）")


class PlatformOrderConfirmCreateIn(BaseModel):
    """
    当单执行：人工确认后生成内部订单（orders）
    - 平台订单已存在，本接口创建的是内部订单
    - 不依赖 PSKU 正确性/不依赖 binding
    - 不写 platform_sku_bindings
    """

    model_config = ConfigDict(extra="ignore")

    platform: constr(min_length=1, max_length=32)
    store_id: int = Field(..., ge=1)
    ext_order_no: constr(min_length=1)

    decisions: List[PlatformOrderManualDecisionIn] = Field(default_factory=list, description="人工决策列表（至少一条）")
    reason: Optional[str] = Field(None, description="人工继续原因（可选）")


class PlatformOrderConfirmCreateOut(BaseModel):
    status: str
    id: Optional[int] = None
    ref: str

    platform: str
    store_id: int
    ext_order_no: str

    manual_override: bool = True
    manual_reason: Optional[str] = None
    manual_batch_id: Optional[str] = Field(
        None,
        description="本次人工救火写入治理事实表的 batch_id（用于追溯/排障）",
    )
    risk_flags: List[str] = Field(default_factory=list)

    facts_n: int = 0
    fulfillment_status: Optional[str] = None
    blocked_reasons: Optional[List[str]] = None
