# app/services/platform_events_handler_impl.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.services._event_writer import EventWriter

from app.services.platform_events_adapters import get_adapter
from app.services.platform_events_classify import classify
from app.services.platform_events_error_log import log_error_isolated
from app.services.platform_events_extractors import extract_ref, extract_shop_id, extract_state
from app.services.platform_events_metrics import inc_error_metric, inc_event_metric

from app.services.platform_events_actions import do_cancel, do_reserve, do_ship


def _assert_no_reservation_payload(obj: Any) -> None:
    """
    硬防线：彻底删除预占概念后，任何 SHIP payload 都不允许携带 reservation / soft_reserve 相关字段。
    目的：防止旧链路/旧平台适配器悄悄把 reservation 结构带回主线。
    """
    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                ks = str(k).lower()
                if "reservation" in ks or "soft_reserve" in ks:
                    raise ValueError(f"SHIP payload contains forbidden key: {k!r}")
                walk(v)
        elif isinstance(x, list):
            for it in x:
                walk(it)
        else:
            return

    walk(obj)


async def handle_event_batch(
    events: List[Dict[str, Any]],
    session: Optional[AsyncSession] = None,
) -> None:
    """
    平台事件编排（硬口径，彻底删除预占概念）：

      - RESERVE：调用 OrderService.reserve（当前语义为 enter_pickable：生成拣货任务/打印队列，不做预占）
      - CANCEL ：调用 OrderService.cancel（取消订单执行态，不做预占释放）
      - SHIP   ：直接调用 OutboundService.commit 扣库存（库存裁决点）
    """
    audit = EventWriter(source="platform-events")

    for raw in events:
        platform = str(raw.get("platform") or "").lower()

        # 每个事件独立一个 trace_id（黑匣子）
        trace = new_trace(f"platform:{platform}:{extract_ref(raw) or extract_state(raw)}")

        try:
            adapter = get_adapter(platform)
            parsed = await adapter.parse_event(raw)
            mapped = await adapter.to_outbound_task(parsed)

            task = {
                "platform": platform,
                "shop_id": mapped.get("shop_id") if isinstance(mapped, dict) else None,
                "ref": mapped.get("ref") if isinstance(mapped, dict) else None,
                "state": mapped.get("state") if isinstance(mapped, dict) else None,
                "lines": mapped.get("lines") if isinstance(mapped, dict) else None,
                "payload": mapped.get("payload") if isinstance(mapped, dict) else None,
                "warehouse_code": (mapped.get("warehouse_code") if isinstance(mapped, dict) else None),
            }

            # 与旧实现一致：fallback 到 raw extractor
            task["shop_id"] = task.get("shop_id") or extract_shop_id(raw)
            task["ref"] = task.get("ref") or extract_ref(raw)
            task["state"] = task.get("state") or extract_state(raw)
            task["lines"] = task.get("lines") or raw.get("lines") or []
            task["payload"] = task.get("payload") or raw

            inc_event_metric(platform, task["shop_id"] or "", task["state"] or "")
            await audit.write_json(
                session,
                level="INFO",
                message={
                    "evt": "event_in",
                    "trace_id": trace.trace_id,
                    "task": {k: task[k] for k in ("platform", "shop_id", "ref", "state")},
                },
            )

            action = classify(task["state"])
            if action == "IGNORE":
                await audit.write_json(
                    session,
                    level="INFO",
                    message={
                        "evt": "event_ignored",
                        "trace_id": trace.trace_id,
                        "platform": platform,
                        "ref": task["ref"],
                        "state": task["state"],
                    },
                )
                continue

            # ---------------- RESERVE ----------------
            if action == "RESERVE":
                n = await do_reserve(session=session, platform=platform, task=task, trace_id=trace.trace_id)
                await audit.write_json(
                    session,
                    level="INFO",
                    message={
                        "evt": "event_reserved",
                        "trace_id": trace.trace_id,
                        "platform": platform,
                        "ref": task["ref"],
                        "lines": int(n),
                    },
                )
                continue

            # ---------------- CANCEL ----------------
            if action == "CANCEL":
                n = await do_cancel(session=session, platform=platform, task=task, trace_id=trace.trace_id)
                await audit.write_json(
                    session,
                    level="INFO",
                    message={
                        "evt": "event_canceled",
                        "trace_id": trace.trace_id,
                        "platform": platform,
                        "ref": task["ref"],
                        "lines": int(n),
                    },
                )
                continue

            # ---------------- SHIP ----------------
            if action == "SHIP":
                n = await do_ship(
                    session=session,
                    platform=platform,
                    raw_event=raw,
                    mapped=mapped,
                    task=task,
                    trace_id=trace.trace_id,
                )
                await audit.write_json(
                    session,
                    level="INFO",
                    message={
                        "evt": "event_shipped",
                        "trace_id": trace.trace_id,
                        "platform": platform,
                        "ref": task["ref"],
                        "lines": int(n),
                    },
                )
                continue

        except Exception as e:
            await audit.write_json(
                session,
                level="ERROR",
                message={
                    "evt": "event_error",
                    "platform": platform,
                    "error": str(e),
                    "trace_id": trace.trace_id,
                },
            )
            inc_error_metric(platform, extract_shop_id(raw), type(e).__name__)
            if session is not None:
                await log_error_isolated(session, platform, raw, e)
            raise
