# app/services/order_lifecycle_v2_build_stages.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.trace_service import TraceEvent
from app.services.order_lifecycle_v2_types import LifecycleStage


def _first(events: List[TraceEvent], pred) -> Optional[TraceEvent]:
    for e in events:
        if pred(e):
            return e
    return None


def build_stages_from_events(events: List[TraceEvent]) -> List[LifecycleStage]:
    if not events:
        return []

    created = _first(events, lambda e: e.source == "order")
    outbound = _first(events, lambda e: e.source == "outbound")

    def _is_shipped(e: TraceEvent) -> bool:
        if e.source == "ledger":
            reason = str((e.raw or {}).get("reason") or "").upper()
            return reason in {"SHIP", "SHIPMENT", "SHIP_OUT", "OUTBOUND_SHIP"}

        if e.source == "audit":
            meta = (e.raw or {}).get("meta") or {}
            flow = str(meta.get("flow") or "").upper()
            event = str(meta.get("event") or "").upper()
            if flow == "OUTBOUND" and event in {"SHIP_COMMIT", "OUTBOUND_SHIP", "SHIP"}:
                return True

        return False

    shipped = _first(events, _is_shipped)

    def _is_returned(e: TraceEvent) -> bool:
        if e.source != "ledger":
            return False
        reason = str((e.raw or {}).get("reason") or "").upper()
        return reason.startswith("RETURN_") or reason == "RECEIPT"

    returned = _first(events, _is_returned)

    stages: List[LifecycleStage] = []

    def _evidence_from_event(e: Optional[TraceEvent]) -> Dict[str, Any] | None:
        if not e:
            return None
        raw = dict(e.raw or {})
        keep_keys = {
            "id",
            "reason",
            "ref",
            "ref_line",
            "item_id",
            "warehouse_id",
            "batch_code",
            "delta",
            "after_qty",
            "platform",
            "shop_id",
            "status",
            "flow",
            "event",
            "meta",
        }
        return {k: v for k, v in raw.items() if k in keep_keys}

    stages.append(
        LifecycleStage(
            key="created",
            label="订单创建",
            ts=created.ts if created else None,
            present=created is not None,
            description=(
                created.summary
                if created
                else "orders 表中未找到订单创建事件（可能尚未 ingest 或 trace_id 断裂）。"
            ),
            source=created.source if created else None,
            ref=created.ref if created else None,
            evidence_type="explicit_order" if created else None,
            evidence=_evidence_from_event(created),
        )
    )

    stages.append(
        LifecycleStage(
            key="outbound",
            label="出库单生成",
            ts=outbound.ts if outbound else None,
            present=outbound is not None,
            description=outbound.summary if outbound else "未检测到 outbound_commits_v2 相关事件。",
            source=outbound.source if outbound else None,
            ref=outbound.ref if outbound else None,
            evidence_type="explicit_outbound_v2" if outbound else None,
            evidence=_evidence_from_event(outbound),
        )
    )

    stages.append(
        LifecycleStage(
            key="shipped",
            label="发运完成",
            ts=shipped.ts if shipped else None,
            present=shipped is not None,
            description=(
                shipped.summary
                if shipped
                else "未检测到发运相关事件（ship ledger 或 OUTBOUND/SHIP_COMMIT 审计）。"
            ),
            source=shipped.source if shipped else None,
            ref=shipped.ref if shipped else None,
            evidence_type=(
                "explicit_ledger_ship"
                if shipped and shipped.source == "ledger"
                else "explicit_audit_ship"
                if shipped and shipped.source == "audit"
                else None
            ),
            evidence=_evidence_from_event(shipped),
        )
    )

    stages.append(
        LifecycleStage(
            key="returned",
            label="退货入库",
            ts=returned.ts if returned else None,
            present=returned is not None,
            description=(
                returned.summary
                if returned
                else "未检测到退货相关的入库记账（如 RETURN_* / RECEIPT）。"
            ),
            source=returned.source if returned else None,
            ref=returned.ref if returned else None,
            evidence_type="explicit_ledger_return" if returned else None,
            evidence=_evidence_from_event(returned),
        )
    )

    # SLA：相对首个已发生节点的耗时
    baseline: Optional[datetime] = None
    for st in stages:
        if st.present and st.ts:
            baseline = st.ts
            break

    if baseline is None:
        return stages

    for st in stages:
        if not st.present or not st.ts:
            continue
        diff_minutes = (st.ts - baseline).total_seconds() / 60.0
        if diff_minutes <= 5:
            st.sla_bucket = "ok"
        elif diff_minutes <= 30:
            st.sla_bucket = "warn"
        else:
            st.sla_bucket = "breach"

    return stages
