# app/api/routers/debug_trace.py
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session
from app.services.trace_service import TraceService

router = APIRouter(prefix="/debug", tags=["debug-trace"])


class TraceEventModel(BaseModel):
    """
    TraceEvent v2 统一模型（后端 → 前端）：

    - ts        : 事件时间（可能为空）
    - source    : 事件来源（ledger / reservation / audit / outbound / order 等）
    - kind      : 事件类型 / 动作名
    - ref       : 业务 ref（订单号 / reservation ref / snapshot job id 等）
    - summary   : 文本摘要（向后兼容）
    - raw       : 原始字段明细（调试用）

    v2 扩展字段（与前端 TraceEvent 类型对齐）：
    - trace_id      : 链路 id
    - warehouse_id  : 仓库维度
    - item_id       : 商品维度
    - batch_code    : 批次维度
    - movement_type : 标准化动作类型 INBOUND/OUTBOUND/COUNT/ADJUST/RETURN/UNKNOWN
    - message       : 展示用摘要（Timeline 优先展示）
    - reason        : 原始 reason 字段（台账等）
    """

    ts: Optional[datetime] = Field(
        None,
        description="事件时间戳（可能为空）",
    )
    source: str = Field(
        ...,
        description="事件来源，例如 ledger / reservation / outbound / audit 等",
    )
    kind: str = Field(
        ...,
        description="事件类型 / 动作名",
    )
    ref: Optional[str] = Field(
        None,
        description="业务 ref（订单号 / reservation ref 等）",
    )
    summary: str = Field(
        ...,
        description="人类可读的事件摘要（向后兼容字段）",
    )
    raw: dict[str, Any] = Field(
        ...,
        description="原始字段明细（调试用）",
    )

    # v2 扩展字段
    trace_id: Optional[str] = Field(
        None,
        description="trace_id（通常与请求参数相同，用于前端直接使用）",
    )
    warehouse_id: Optional[int] = Field(
        None,
        description="仓库 ID（若事件包含该维度）",
    )
    item_id: Optional[int] = Field(
        None,
        description="商品 ID（若事件包含该维度）",
    )
    batch_code: Optional[str] = Field(
        None,
        description="批次编码（若事件包含该维度）",
    )
    movement_type: Optional[str] = Field(
        None,
        description=("标准化动作类型：INBOUND / OUTBOUND / COUNT / ADJUST / RETURN / UNKNOWN 等"),
    )
    message: Optional[str] = Field(
        None,
        description="人类可读摘要（前端 Timeline 优先展示）",
    )
    reason: Optional[str] = Field(
        None,
        description="原始 reason 字段（例如台账 reason）",
    )


class TraceResponseModel(BaseModel):
    trace_id: str
    warehouse_id: Optional[int] = Field(
        None,
        description="若指定，则 events 已按该 warehouse 过滤（但保留无仓的全局事件）",
    )
    events: List[TraceEventModel]


def _infer_movement_type(reason: Optional[str]) -> Optional[str]:
    """
    根据 reason 推断标准化 movement_type，用于前端统一展示。
    """
    if not reason:
        return None
    r = reason.upper()

    # 入库类
    if r in {"RECEIPT", "INBOUND", "INBOUND_RECEIPT"}:
        return "INBOUND"

    # 出库 / 发货类
    if r in {"SHIP", "SHIPMENT", "OUTBOUND_SHIP", "OUTBOUND_COMMIT"}:
        return "OUTBOUND"

    # 盘点类
    if r in {"COUNT", "STOCK_COUNT", "INVENTORY_COUNT"}:
        return "COUNT"

    # 调整类
    if r in {"ADJUSTMENT", "ADJUST", "MANUAL_ADJUST"}:
        return "ADJUST"

    # 退货 / 逆向
    if r in {"RETURN", "RMA", "INBOUND_RETURN"}:
        return "RETURN"

    # 其他暂标记为 UNKNOWN，方便从真实数据中逐步细化
    return "UNKNOWN"


def _filter_events_by_warehouse(
    events: List[TraceEventModel],
    warehouse_id: Optional[int],
) -> List[TraceEventModel]:
    """
    按 warehouse_id 过滤事件：

    - warehouse_id 为 None：不过滤；
    - warehouse_id 有值：
        * 若事件本身有 warehouse_id 字段，则要求其等于指定值；
        * 若事件本身无 warehouse 维度，则视为“全局事件”，仍保留。
    """
    if warehouse_id is None:
        return events

    filtered: List[TraceEventModel] = []
    for e in events:
        # 优先使用标准字段
        wid = e.warehouse_id
        if wid is None:
            # 向后兼容：从 raw 中兜底尝试
            raw = e.raw or {}
            wid = raw.get("warehouse_id") or raw.get("warehouse") or raw.get("wh_id")

        # 无仓信息 → 全局事件，保留；有仓信息 → 必须匹配指定仓
        if wid is None or wid == warehouse_id:
            filtered.append(e)

    return filtered


@router.get(
    "/trace/{trace_id}",
    response_model=TraceResponseModel,
)
async def get_trace(
    trace_id: str = Path(..., description="trace 唯一标识"),
    warehouse_id: Optional[int] = Query(
        None,
        description=("可选：指定 warehouse_id 后，只保留该仓的事件，以及无仓的全局事件。"),
    ),
    session: AsyncSession = Depends(get_session),
) -> TraceResponseModel:
    """
    Trace 黑盒接口：根据 trace_id 聚合 event_store / audit_events / reservations /
    stock_ledger / orders / outbound_commits_v2 等多表事件。

    - 无 warehouse_id：返回全链事件列表（与原有行为保持兼容）；
    - 有 warehouse_id：仅保留该仓的事件（ledger/reservation/outbound 等），
      以及无仓信息的全局事件（如 orders、部分 audit）。
    """
    svc = TraceService(session)
    result = await svc.get_trace(trace_id)

    v2_events: List[TraceEventModel] = []

    for e in result.events:
        raw = e.raw or {}

        # 尝试从 raw 中解析三维库存维度
        wh = raw.get("warehouse_id") or raw.get("warehouse") or raw.get("wh_id")
        item_id = raw.get("item_id")
        batch_code = raw.get("batch_code")

        # 尝试提取 reason
        reason_raw = raw.get("reason")
        reason = str(reason_raw) if reason_raw is not None else None
        if reason is not None and not reason.strip():
            reason = None

        movement_type = _infer_movement_type(reason) if reason else None

        # message：优先用 summary，其次 reason，再次 kind
        message = e.summary or reason or e.kind

        v2_events.append(
            TraceEventModel(
                ts=e.ts,
                source=e.source,
                kind=e.kind,
                ref=e.ref,
                summary=e.summary,
                raw=raw,
                trace_id=trace_id,
                warehouse_id=wh if isinstance(wh, int) else None,
                item_id=item_id if isinstance(item_id, int) else None,
                batch_code=batch_code if isinstance(batch_code, str) else None,
                movement_type=movement_type,
                message=message,
                reason=reason,
            )
        )

    events = _filter_events_by_warehouse(v2_events, warehouse_id)

    return TraceResponseModel(
        trace_id=trace_id,
        warehouse_id=warehouse_id,
        events=events,
    )
