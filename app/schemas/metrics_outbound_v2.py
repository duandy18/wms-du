# app/schemas/metrics_outbound_v2.py

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel

# --------- 基础：单日总览（已在用） -----------------


class OutboundDistributionPoint(BaseModel):
    hour: str  # '09' / '10' / ...
    orders: int  # 当小时 ORDER_CREATED 数
    pick_qty: int  # 当小时拣货件数


class OutboundMetricsV2(BaseModel):
    """
    单日 + 单平台的出库指标大盘：
    - total_orders      总订单数（ORDER_CREATED）
    - success_orders    成功订单数（SHIP_COMMIT）
    - success_rate      成功率（%）

    - fallback_times    fallback 次数
    - fallback_rate     fallback 占比（%）

    - fefo_hit_rate     FEFO 命中率（%）

    - distribution      当天按小时的出库分布（orders + pick_qty）
    """

    day: date
    platform: str

    total_orders: int
    success_orders: int
    success_rate: float

    fallback_times: int
    fallback_rate: float

    fefo_hit_rate: float

    distribution: List[OutboundDistributionPoint] = []


# --------- 1) 趋势 / 多日范围 ------------------------


class OutboundDaySummary(BaseModel):
    day: date
    total_orders: int
    success_rate: float
    fallback_rate: float
    fefo_hit_rate: float


class OutboundRangeMetricsResponse(BaseModel):
    platform: str
    days: List[OutboundDaySummary]


# --------- 2) 仓库维度拆分 ---------------------------


class OutboundWarehouseMetric(BaseModel):
    warehouse_id: int
    total_orders: int
    success_orders: int
    success_rate: float
    pick_qty: int


class OutboundWarehouseMetricsResponse(BaseModel):
    day: date
    platform: str
    warehouses: List[OutboundWarehouseMetric]


# --------- 3) 出库失败诊断 ---------------------------


class OutboundFailureDetail(BaseModel):
    ref: str
    trace_id: Optional[str] = None
    fail_point: str  # ROUTING_FAIL / PICK_FAIL / SHIP_FAIL / INVENTORY_FAIL / UNKNOWN
    message: Optional[str] = None


class OutboundFailuresMetricsResponse(BaseModel):
    day: date
    platform: str
    routing_failed: int
    pick_failed: int
    ship_failed: int
    inventory_insufficient: int
    details: List[OutboundFailureDetail] = []


# --------- 4) FEFO 风险监控 --------------------------


class FefoItemRisk(BaseModel):
    item_id: int
    sku: str
    name: str
    near_expiry_batches: int
    fefo_hit_rate_7d: float
    risk_score: float  # 用于排序的简单分数（0-100）


class FefoRiskMetricsResponse(BaseModel):
    as_of: date
    items: List[FefoItemRisk]


# --------- 5) 多店铺维度 -----------------------------


class OutboundShopMetric(BaseModel):
    shop_id: str
    total_orders: int
    success_orders: int
    success_rate: float
    fallback_times: int
    fallback_rate: float


class OutboundShopMetricsResponse(BaseModel):
    day: date
    platform: str
    shops: List[OutboundShopMetric]
