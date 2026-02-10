# app/api/routers/platform_orders_ingest_schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, constr


class PlatformOrderLineIn(BaseModel):
    """
    Phase N+2 · 平台订单行输入

    说明：
    - filled_code 为推荐字段（Phase N+2 语义）
    - 二者均可缺失，是否可执行由 resolver 判定（而非 schema 阶段）
    """

    model_config = ConfigDict(extra="ignore")

    # Phase N+2 推荐字段（不可在 schema 阶段强制必填）
    filled_code: Optional[str] = Field(
        None,
        description="商家后台填写码（Phase N+2 推荐字段）",
    )

    # legacy 兼容字段（历史名称）

    qty: int = Field(default=1, gt=0, description="数量（>0）")
    title: Optional[str] = Field(None, description="商品标题（可选）")
    spec: Optional[str] = Field(None, description="规格描述（可选）")
    extras: Optional[Dict[str, Any]] = Field(None, description="行级扩展字段")


class PlatformOrderIngestIn(BaseModel):
    """
    Phase N+2 · 平台订单接入（宽进严出）
    """

    model_config = ConfigDict(extra="ignore")

    platform: constr(min_length=1, max_length=32)

    # 内部优先
    store_id: Optional[int] = None

    # 外部兼容
    shop_id: Optional[constr(min_length=1)] = None

    ext_order_no: constr(min_length=1)
    occurred_at: Optional[datetime] = None

    buyer_name: Optional[str] = None
    buyer_phone: Optional[str] = None

    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None
    zipcode: Optional[str] = None

    lines: List[PlatformOrderLineIn] = Field(
        default_factory=list,
        description="订单行列表（可含 legacy 形态行）",
    )

    store_name: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None


class PlatformOrderLineResult(BaseModel):
    """
    行级解析结果（Phase N+2 输出）
    """

    filled_code: Optional[str] = None

    # deprecated alias

    qty: int
    reason: Optional[str] = None
    hint: Optional[str] = None
    fsku_id: Optional[int] = None
    expanded_items: Optional[List[Dict[str, Any]]] = None
    risk_flags: Optional[List[str]] = None
    risk_level: Optional[str] = None
    risk_reason: Optional[str] = None

    # ✅ 新增：给前端的“下一步动作”（用于人工救火闭环）
    next_actions: Optional[List[Dict[str, Any]]] = None


class PlatformOrderIngestOut(BaseModel):
    status: str
    id: Optional[int]
    ref: str

    store_id: Optional[int]

    resolved: List[PlatformOrderLineResult] = Field(default_factory=list)
    unresolved: List[PlatformOrderLineResult] = Field(default_factory=list)
    facts_written: int

    fulfillment_status: Optional[str] = None
    blocked_reasons: Optional[List[str]] = None

    allow_manual_continue: bool = False
    risk_flags: List[str] = Field(default_factory=list)
    risk_level: Optional[str] = None
    risk_reason: Optional[str] = None
