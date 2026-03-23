# app/tms/pricing/runtime_policy.py

from __future__ import annotations

from datetime import datetime
from typing import Literal


PricingStatus = Literal[
    "provider_disabled",
    "no_active_template",
    "binding_disabled",
    "scheduled",
    "active",
]


def compute_pricing_status(
    *,
    provider_active: bool,
    binding_active: bool,
    active_template_id: int | None,
    effective_from: datetime | None,
    now: datetime,
) -> PricingStatus:
    """
    运行态状态机（唯一事实源）

    判定优先级（非常重要）：

    1. provider_disabled
    2. no_active_template
    3. binding_disabled
    4. scheduled
    5. active
    """

    # 1️⃣ 承运商已停用
    if not provider_active:
        return "provider_disabled"

    # 2️⃣ 未挂收费表
    if active_template_id is None:
        return "no_active_template"

    # 3️⃣ binding 已停用
    if not binding_active:
        return "binding_disabled"

    # 4️⃣ 待生效（时间未到）
    if effective_from is not None and effective_from > now:
        return "scheduled"

    # 5️⃣ 已生效
    return "active"
