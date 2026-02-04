# app/api/routers/orders_fulfillment_debug_schemas.py
from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

FULFILLMENT_DEBUG_VERSION = "v4-min"


class FulfillmentDebugAddress(BaseModel):
    # 仅保留“归属仓判断”最低字段
    province: Optional[str] = None
    city: Optional[str] = None
    district: Optional[str] = None
    detail: Optional[str] = None


class FulfillmentServiceDebug(BaseModel):
    """
    服务仓命中诊断（当前配置事实）：
    - hit=False：city_code 未配置服务仓
    - hit=True ：给出 service_warehouse_id
    """
    province_code: Optional[str] = None
    city_code: Optional[str] = None
    hit: bool = False
    service_warehouse_id: Optional[int] = None
    reason: Optional[str] = None  # OK / CITY_MISSING / NO_SERVICE_WAREHOUSE


class FulfillmentDebugOut(BaseModel):
    """
    v4-min：只回答“归属仓是谁”
    - 不返回 fulfillment_status / blocked_reasons（blocked 事实由订单履约快照表承载）
    - 不返回 candidates / scan / check（全部砍掉）
    """
    version: str = FULFILLMENT_DEBUG_VERSION

    order_id: int
    platform: str
    shop_id: str
    ext_order_no: Optional[str] = None

    address: FulfillmentDebugAddress = Field(default_factory=FulfillmentDebugAddress)
    service: FulfillmentServiceDebug = Field(default_factory=FulfillmentServiceDebug)

    summary: Dict[str, Any] = Field(default_factory=dict)
