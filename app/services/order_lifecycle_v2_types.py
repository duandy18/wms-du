# app/services/order_lifecycle_v2_types.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

SlaBucket = Literal["ok", "warn", "breach"]
HealthBucket = Literal["OK", "WARN", "BAD"]


@dataclass
class LifecycleStage:
    """
    订单生命周期阶段（v2，基于 trace_id 推断，纯“表驱动版”）：

    - key           : created / reserved / reserved_consumed / outbound / shipped / returned / delivered
    - label         : 中文标签
    - ts            : 事件时间（可能为 None）
    - present       : 是否存在该阶段
    - description   : 解释说明（不再提及 ref/fallback）
    - source        : 事件来源（ledger / reservation / outbound / audit / order / reservation_consumed / shipping_records）
    - ref           : 业务 ref（仅作展示，生命周期逻辑不依赖它）
    - sla_bucket    : SLA 粗分级（ok / warn / breach）
    - evidence_type : 证据类型（explicit_*）
    - evidence      : 原始字段（裁剪版 raw，方便前端 Tooltip 展示）
    """

    key: str
    label: str
    ts: Optional[datetime]
    present: bool
    description: str
    source: Optional[str] = None
    ref: Optional[str] = None
    sla_bucket: Optional[SlaBucket] = None
    evidence_type: Optional[str] = None
    evidence: Dict[str, Any] | None = None


@dataclass
class LifecycleSummary:
    """
    生命周期整体诊断：
    - health : OK / WARN / BAD
    - issues : 文本列表，描述发现的问题
    """

    health: HealthBucket
    issues: List[str]
