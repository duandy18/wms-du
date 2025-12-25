# app/services/order_lifecycle_v2_build_summary.py
from __future__ import annotations

from typing import Dict, List

from app.services.order_lifecycle_v2_types import HealthBucket, LifecycleStage, LifecycleSummary


def summarize_stages(stages: List[LifecycleStage]) -> LifecycleSummary:
    issues: List[str] = []
    stage_by_key: Dict[str, LifecycleStage] = {st.key: st for st in stages}

    created = stage_by_key.get("created")
    reserved = stage_by_key.get("reserved")
    reserved_consumed = stage_by_key.get("reserved_consumed")
    outbound = stage_by_key.get("outbound")
    shipped = stage_by_key.get("shipped")
    returned = stage_by_key.get("returned")
    delivered = stage_by_key.get("delivered")

    if not created or not created.present:
        issues.append("订单创建节点缺失（orders 无记录或 trace 断裂）。")

    if created and created.present:
        later_present = any(
            getattr(st, "present", False)
            for st in (reserved_consumed, outbound, shipped, returned, delivered)
        )
        if (not reserved or not reserved.present) and later_present:
            issues.append("存在后续生命周期事件，但缺少预占创建记录（reservations）。")

    if reserved and reserved.present and not (reserved_consumed and reserved_consumed.present):
        issues.append("预占已创建但未检测到消耗记录（reservation_consumed 事件）。")

    if outbound and outbound.present and not (shipped and shipped.present):
        issues.append("已有出库相关事件，但未检测到发运完成事件（ship ledger / audit）。")

    has_breach = any(st.sla_bucket == "breach" for st in stages if st.present)
    has_warn = any(st.sla_bucket == "warn" for st in stages if st.present)

    if has_breach:
        issues.append("至少一个阶段的 SLA 已超时。")
    elif has_warn:
        issues.append("至少一个阶段的 SLA 接近超时。")

    if not stages:
        health: HealthBucket = "WARN"
        issues.append("当前 trace 下未找到任何生命周期节点。")
    elif any(kw in iss for iss in issues for kw in ["缺失", "超时", "未检测到"]) and has_breach:
        health = "BAD"
    elif issues:
        health = "WARN"
    else:
        health = "OK"

    return LifecycleSummary(health=health, issues=issues)
