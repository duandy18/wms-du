# app/api/routers/platform_orders_confirm_create_schemas.py
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Phase N+4 · Input Schemas (line locator separation)
# ---------------------------------------------------------------------------

class PlatformOrderConfirmCreateDecisionIn(BaseModel):
    """
    Phase N+4 · 人工决策输入（单行）

    说明：
    - filled_code 是“填写码”唯一语义字段
    - line_key 是内部幂等锚点（不推荐外部使用）
    - locator_kind/locator_value 是对外定位语义（推荐）
      * FILLED_CODE + filled_code
      * LINE_NO + str(line_no)
    """

    # internal / legacy (kept for backward compatibility)
    line_key: Optional[str] = None
    line_no: Optional[int] = None

    # semantic locator (recommended)
    locator_kind: Optional[str] = Field(
        None,
        description="对外定位类型（推荐）：FILLED_CODE / LINE_NO",
    )
    locator_value: Optional[str] = Field(
        None,
        description="对外定位值（推荐）：当 FILLED_CODE 时为 filled_code；当 LINE_NO 时为 line_no 文本",
    )

    filled_code: Optional[str] = Field(
        None,
        description="商家后台填写码（推荐；唯一语义字段）",
    )

    # legacy / internal compat field (explicitly rejected by router/shared if present)
    platform_sku_id: Optional[str] = Field(
        None,
        description="已废弃：出现即报错（请使用 filled_code）",
    )

    item_id: int
    qty: int
    note: Optional[str] = None


class PlatformOrderConfirmCreateIn(BaseModel):
    """
    Phase N+4 · 当单执行（人工确认后创建订单）

    解析语义：
    - 决策行优先使用 locator（locator_kind/value）
    - 其次使用 filled_code / line_no
    - line_key 仅作为旧链路兼容
    """

    platform: str
    store_id: int
    ext_order_no: str

    reason: Optional[str] = None

    decisions: List[PlatformOrderConfirmCreateDecisionIn] = Field(
        default_factory=list,
        description="人工决策行列表",
    )


# ---------------------------------------------------------------------------
# Legacy / Internal Schemas（仅供内部链路使用）
# ---------------------------------------------------------------------------

class PlatformOrderManualDecisionIn(BaseModel):
    """
    【deprecated / internal】

    内部使用的人工决策输入结构：
    - 支持 locator_kind/value（推荐）
    - 支持 filled_code/line_no（语义定位）
    - line_key 仅作为旧链路兼容
    - platform_sku_id 已废弃：出现即报错
    """

    line_key: Optional[str] = None
    line_no: Optional[int] = None

    locator_kind: Optional[str] = None
    locator_value: Optional[str] = None

    filled_code: Optional[str] = None
    platform_sku_id: Optional[str] = None

    item_id: int
    qty: int
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Output Schemas
# ---------------------------------------------------------------------------

class PlatformOrderConfirmCreateDecisionOut(BaseModel):
    """
    Phase N+4 · 人工决策明细（输出）

    说明：
    - filled_code 为唯一语义字段
    - locator_kind/value 为推荐定位语义（与 line_key 分层）
    """

    filled_code: Optional[str] = Field(
        None,
        description="商家后台填写码（唯一语义字段）",
    )

    locator_kind: Optional[str] = Field(
        None,
        description="对外定位类型（推荐）：FILLED_CODE / LINE_NO",
    )
    locator_value: Optional[str] = Field(
        None,
        description="对外定位值（推荐）",
    )

    # internal / legacy (still output for compatibility)
    line_key: Optional[str] = None
    line_no: Optional[int] = None
    item_id: Optional[int] = None
    qty: Optional[int] = None
    fact_qty: Optional[int] = None
    note: Optional[str] = None


class PlatformOrderConfirmCreateOut(BaseModel):
    status: str
    id: Optional[int]
    ref: str

    platform: str
    store_id: int
    ext_order_no: str

    manual_override: bool
    manual_reason: Optional[str] = None
    manual_batch_id: Optional[str] = None

    decisions: List[PlatformOrderConfirmCreateDecisionOut] = Field(default_factory=list)

    risk_flags: List[str] = Field(default_factory=list)
    facts_n: int

    fulfillment_status: Optional[str] = None
    blocked_reasons: Optional[List[str]] = None
