# app/services/order_lifecycle_v2.py
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.trace_service import TraceEvent, TraceService

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


def _first(events: List[TraceEvent], pred) -> Optional[TraceEvent]:
    for e in events:
        if pred(e):
            return e
    return None


def _build_stages_from_events(events: List[TraceEvent]) -> List[LifecycleStage]:
    if not events:
        return []

    # ---- 基础查找（全部基于 source 字段，完全不看 ref/fallback） ----
    created = _first(events, lambda e: e.source == "order")
    reserved = _first(events, lambda e: e.source == "reservation")
    reserved_consumed = _first(events, lambda e: e.source == "reservation_consumed")

    # outbound：只认 outbound_commits_v2（source="outbound"）
    outbound = _first(events, lambda e: e.source == "outbound")

    # shipped：两类证据
    # 1. ledger 上真正的发运类台账（少数路径可能存在 SHIP/SHIPMENT）
    # 2. audit_events 中 OUTBOUND/SHIP_COMMIT 事件（当前 v2 主要发运证据）
    def _is_shipped(e: TraceEvent) -> bool:
        # 1) ledger: SHIP 系列
        if e.source == "ledger":
            reason = str((e.raw or {}).get("reason") or "").upper()
            return reason in {
                "SHIP",
                "SHIPMENT",
                "SHIP_OUT",
                "OUTBOUND_SHIP",
            }

        # 2) audit: flow=OUTBOUND, event=SHIP_COMMIT（ShipService.commit 写入）
        if e.source == "audit":
            meta = (e.raw or {}).get("meta") or {}
            flow = str(meta.get("flow") or "").upper()
            event = str(meta.get("event") or "").upper()
            if flow == "OUTBOUND" and event in {
                "SHIP_COMMIT",
                "OUTBOUND_SHIP",
                "SHIP",
            }:
                return True

        return False

    shipped = _first(events, _is_shipped)

    # returned：ledger.reason 以 RETURN_ 开头 或 RECEIPT
    def _is_returned(e: TraceEvent) -> bool:
        if e.source != "ledger":
            return False
        reason = str((e.raw or {}).get("reason") or "").upper()
        return reason.startswith("RETURN_") or reason == "RECEIPT"

    returned = _first(events, _is_returned)

    # ---- 组装阶段 ----
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
            key="reserved",
            label="预占创建",
            ts=reserved.ts if reserved else None,
            present=reserved is not None,
            description=(
                reserved.summary
                if reserved
                else "reservations 表中未找到该 trace_id 对应的预占记录。"
            ),
            source=reserved.source if reserved else None,
            ref=reserved.ref if reserved else None,
            evidence_type="explicit_reservation" if reserved else None,
            evidence=_evidence_from_event(reserved),
        )
    )

    stages.append(
        LifecycleStage(
            key="reserved_consumed",
            label="预占消耗",
            ts=reserved_consumed.ts if reserved_consumed else None,
            present=reserved_consumed is not None,
            description=(
                reserved_consumed.summary
                if reserved_consumed
                else "未检测到预占被消耗的证据（reservation_consumed 事件）。"
            ),
            source=reserved_consumed.source if reserved_consumed else None,
            ref=reserved_consumed.ref if reserved_consumed else None,
            evidence_type="explicit_reservation_consumed" if reserved_consumed else None,
            evidence=_evidence_from_event(reserved_consumed),
        )
    )

    stages.append(
        LifecycleStage(
            key="outbound",
            label="出库单生成",
            ts=outbound.ts if outbound else None,
            present=outbound is not None,
            description=(
                outbound.summary if outbound else "未检测到 outbound_commits_v2 相关事件。"
            ),
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

    # ---- SLA：相对首个已发生节点的耗时 ----
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


def _inject_delivered_stage(
    stages: List[LifecycleStage],
    *,
    ts: Optional[datetime],
    ref: Optional[str],
) -> List[LifecycleStage]:
    """
    根据 shipping_records(status=DELIVERED) 注入一个 delivered 阶段。

    - 若已经存在 key="delivered" 的阶段，则不重复注入；
    - 若 delivery_time 为空，则不注入。
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

    # 不强制插入到某个特定位置，直接追加，前端可按 ts 排序展示。
    stages.append(delivered_stage)
    return stages


def _summarize_stages(stages: List[LifecycleStage]) -> LifecycleSummary:
    """
    粗粒度诊断（同样不依赖 ref/fallback）：
      - health:
          * BAD  : 存在严重缺失 / 明确超时
          * WARN : 部分阶段缺失 / SLA warn
          * OK   : 整体正常
      - issues: 文本列表
    """
    issues: List[str] = []

    stage_by_key: Dict[str, LifecycleStage] = {st.key: st for st in stages}

    created = stage_by_key.get("created")
    reserved = stage_by_key.get("reserved")
    reserved_consumed = stage_by_key.get("reserved_consumed")
    outbound = stage_by_key.get("outbound")
    shipped = stage_by_key.get("shipped")
    returned = stage_by_key.get("returned")
    delivered = stage_by_key.get("delivered")  # 目前仅用于显示，不强参与错误判断

    # 1) 核心阶段缺失
    if not created or not created.present:
        issues.append("订单创建节点缺失（orders 无记录或 trace 断裂）。")

    # 有后续阶段但缺 reserved（意味着链路起点有问题）
    if created and created.present:
        later_present = any(
            st.present for st in [reserved_consumed, outbound, shipped, returned, delivered]
        )
        if (not reserved or not reserved.present) and later_present:
            issues.append("存在后续生命周期事件，但缺少预占创建记录（reservations）。")

    # 2) 预占消耗缺失
    if reserved and reserved.present and not (reserved_consumed and reserved_consumed.present):
        issues.append("预占已创建但未检测到消耗记录（reservation_consumed 事件）。")

    # 3) 发运缺失（只在存在 outbound 或明显 ship 证据时检查）
    if outbound and outbound.present and not (shipped and shipped.present):
        issues.append("已有出库相关事件，但未检测到发运完成事件（ship ledger / audit）。")

    # 4) SLA 相关
    has_breach = any(st.sla_bucket == "breach" for st in stages if st.present)
    has_warn = any(st.sla_bucket == "warn" for st in stages if st.present)

    if has_breach:
        issues.append("至少一个阶段的 SLA 已超时。")
    elif has_warn:
        issues.append("至少一个阶段的 SLA 接近超时。")

    # 5) 简单健康分级
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


class OrderLifecycleV2Service:
    """
    v2 生命周期服务：统一基于 trace_id 推断（纯表驱动版）。

    本次扩展：
    - 通过 shipping_records(status=DELIVERED) 注入 delivered 阶段，
      使生命周期能够一直展示到“订单送达”。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._trace_service = TraceService(session)

    async def _load_delivered_info(
        self,
        trace_id: str,
    ) -> Tuple[Optional[datetime], Optional[str]]:
        """
        从 shipping_records 里查找 status=DELIVERED 且 delivery_time 不为空的记录，
        返回一条最早的送达时间及其 order_ref。
        """
        sql = text(
            """
            SELECT delivery_time, order_ref
              FROM shipping_records
             WHERE trace_id = :tid
               AND status = 'DELIVERED'
               AND delivery_time IS NOT NULL
             ORDER BY delivery_time ASC, id ASC
             LIMIT 1
            """
        )
        res = await self.session.execute(sql, {"tid": trace_id})
        row = res.mappings().first()
        if not row:
            return None, None
        return row["delivery_time"], row["order_ref"]

    async def for_trace_id(self, trace_id: str) -> List[LifecycleStage]:
        result = await self._trace_service.get_trace(trace_id)
        stages = _build_stages_from_events(result.events)

        # 尝试注入 delivered 阶段（基于 shipping_records）
        delivered_ts, delivered_ref = await self._load_delivered_info(trace_id)
        if delivered_ts is not None:
            stages = _inject_delivered_stage(
                stages,
                ts=delivered_ts,
                ref=delivered_ref,
            )

        return stages

    async def for_trace_id_with_summary(
        self, trace_id: str
    ) -> Tuple[List[LifecycleStage], LifecycleSummary]:
        stages = await self.for_trace_id(trace_id)
        summary = _summarize_stages(stages)
        return stages, summary

    async def for_trace_id_as_dicts(self, trace_id: str) -> Dict[str, Any]:
        stages, summary = await self.for_trace_id_with_summary(trace_id)
        return {
            "trace_id": trace_id,
            "stages": [asdict(s) for s in stages],
            "summary": asdict(summary),
        }
