# app/services/order_lifecycle_v2_build_delivered.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from app.services.order_lifecycle_v2_types import LifecycleStage


def inject_delivered_stage(
    stages: List[LifecycleStage],
    *,
    ts: Optional[datetime],
    ref: Optional[str],
) -> List[LifecycleStage]:
    """
    根据 shipping_records(status=DELIVERED) 注入一个 delivered 阶段。
    """
    if ts is None:
        return stages
    if any(st.key == "delivered" for st in stages):
        return stages

    delivered_stage = LifecycleStage(
        key="delivered",
        label="订单送达",
        ts=ts,
        present=True,
        description="基于 shipping_records(status=DELIVERED) 推断的送达时间。",
        source="shipping_records",
        ref=ref,
        evidence_type="explicit_shipping_record",
        evidence={
            "ref": ref,
            "status": "DELIVERED",
            "source": "shipping_records",
        },
    )

    stages.append(delivered_stage)
    return stages
