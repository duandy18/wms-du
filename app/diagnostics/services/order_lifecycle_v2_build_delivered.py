# app/diagnostics/services/order_lifecycle_v2_build_delivered.py
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from app.diagnostics.services.order_lifecycle_v2_types import LifecycleStage


def inject_delivered_stage(
    stages: List[LifecycleStage],
    *,
    ts: Optional[datetime],
    ref: Optional[str],
) -> List[LifecycleStage]:
    """
    delivered 阶段注入逻辑已废止。

    当前终态：
    - 运输生命周期在 shipped（交运完成）处收口；
    - delivered / lost / returned / 在途等后续物流状态，不再由本地 shipping_records 承担真相；
    - 若业务需要查看物流后续状态，应通过平台商铺 API / 平台事件侧获取。

    保留本函数仅作为过渡空实现，避免历史 import 立即失效。
    """
    del ts
    del ref
    return stages
