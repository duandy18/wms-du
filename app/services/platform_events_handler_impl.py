# app/services/platform_events_handler_impl.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.services._event_writer import EventWriter
from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService
from app.services.soft_reserve_service import SoftReserveService
from app.services.store_service import StoreService

from app.services.platform_events_adapters import get_adapter
from app.services.platform_events_classify import classify, merge_lines
from app.services.platform_events_error_log import log_error_isolated
from app.services.platform_events_extractors import extract_ref, extract_shop_id, extract_state
from app.services.platform_events_metrics import inc_error_metric, inc_event_metric

try:
    from app.models.warehouse import WarehouseCode
except Exception:

    class WarehouseCode:  # type: ignore
        MAIN = "MAIN"


async def handle_event_batch(
    events: List[Dict[str, Any]],
    session: Optional[AsyncSession] = None,
) -> None:
    """
    平台事件编排（硬口径）：

      - RESERVE：调用 OrderService.reserve → 落 soft reserve + anti-oversell
      - CANCEL ：调用 OrderService.cancel  → 释放 soft reserve
      - SHIP   ：优先消费 soft reserve（ReservationConsumer.pick_consume）；
                 若没有 reservation 再调用 OutboundService.commit 扣库存。
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
                "shop_id": mapped.get("shop_id") or extract_shop_id(raw),
                "ref": mapped.get("ref") or extract_ref(raw),
                "state": mapped.get("state") or extract_state(raw),
                "lines": mapped.get("lines") or raw.get("lines") or [],
                "payload": mapped.get("payload") or raw,
                "warehouse_code": (
                    mapped.get("warehouse_code") if isinstance(mapped, dict) else None
                ),
            }

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
                if not task["ref"]:
                    raise ValueError("Missing ref for RESERVE")

                lines = [
                    {"item_id": int(x["item_id"]), "qty": int(x["qty"])}
                    for x in (task["lines"] or [])
                    if "item_id" in x and "qty" in x
                ]

                await OrderService.reserve(
                    session,
                    platform=platform,
                    shop_id=task["shop_id"],
                    ref=task["ref"],
                    lines=lines,
                    trace_id=trace.trace_id,
                )
                await audit.write_json(
                    session,
                    level="INFO",
                    message={
                        "evt": "event_reserved",
                        "trace_id": trace.trace_id,
                        "platform": platform,
                        "ref": task["ref"],
                        "lines": len(lines),
                    },
                )
                continue

            # ---------------- CANCEL ----------------
            if action == "CANCEL":
                if not task["ref"]:
                    raise ValueError("Missing ref for CANCEL")

                lines = [
                    {"item_id": int(x["item_id"]), "qty": int(x["qty"])}
                    for x in (task["lines"] or [])
                    if "item_id" in x and "qty" in x
                ]

                await OrderService.cancel(
                    session,
                    platform=platform,
                    shop_id=task["shop_id"],
                    ref=task["ref"],
                    lines=lines,
                    trace_id=trace.trace_id,
                )
                await audit.write_json(
                    session,
                    level="INFO",
                    message={
                        "evt": "event_canceled",
                        "trace_id": trace.trace_id,
                        "platform": platform,
                        "ref": task["ref"],
                        "lines": len(lines),
                    },
                )
                continue

            # ---------------- SHIP ----------------
            if action == "SHIP":
                if not task["ref"]:
                    raise ValueError("Missing ref for SHIP")

                raw_lines = raw.get("lines") or []

                def has_all(arr: object) -> bool:
                    if not arr:
                        return False
                    required_keys = {"item_id", "warehouse_id", "batch_code", "qty"}
                    return all(
                        required_keys.issubset(x.keys())  # type: ignore[arg-type]
                        for x in arr  # type: ignore[assignment]
                    )

                # ⭐ 核心改动在这里：
                # 优先使用新 world 的 ship_lines（location_hint），
                # 若不存在则回退到 legacy 的 ship_lines_legacy。
                mapped_ship = None
                if isinstance(mapped, dict):
                    mapped_ship = (
                        mapped.get("ship_lines")
                    )

                mapped_lines = mapped.get("lines") if isinstance(mapped, dict) else None

                chosen = (
                    raw_lines
                    if has_all(raw_lines)
                    else (mapped_ship or mapped_lines or task.get("lines") or [])
                )

                lines = [
                    {
                        "item_id": int(x["item_id"]),
                        "warehouse_id": int(x["warehouse_id"]),
                        "batch_code": str(x["batch_code"]),
                        "qty": int(x["qty"]),
                    }
                    for x in chosen
                    if {"item_id", "warehouse_id", "batch_code", "qty"}.issubset(x.keys())
                ]
                if not lines:
                    raise ValueError(
                        "No valid ship lines (need item_id, warehouse_id, batch_code, qty)"
                    )

                # 先按 (item,wh,batch) 合并，供 OutboundService 使用
                lines = merge_lines(lines)

                occurred_at = datetime.now(timezone.utc)
                wh_code = str(
                    (mapped.get("warehouse_code") if isinstance(mapped, dict) else None)
                    or task.get("warehouse_code")
                    or getattr(WarehouseCode, "MAIN", "MAIN")
                )

                # Step 1: 先尝试消费 soft reserve
                soft_svc = SoftReserveService()
                platform_db = platform.upper()

                wh_for_reserve = await StoreService.resolve_default_warehouse_for_platform_shop(
                    session,
                    platform=platform_db,
                    shop_id=task["shop_id"],
                )

                # ✅ 关键改造：消费候选仓 = [默认仓（若有）] + [事件 lines 中显式 warehouse_id（location_hint）]
                wh_candidates: List[int] = []
                if wh_for_reserve is not None:
                    try:
                        wh_candidates.append(int(wh_for_reserve))
                    except Exception:
                        pass

                # 从 lines 中提取 distinct warehouse_id（location_hint）
                for x in lines:
                    try:
                        wid = int(x["warehouse_id"])
                    except Exception:
                        continue
                    if wid not in wh_candidates:
                        wh_candidates.append(wid)

                reserve_used = False
                if not wh_candidates:
                    # ✅ 仍然禁止隐性 fallback：既无默认仓，也无显式 location_hint，则不 consume reserve
                    await audit.write_json(
                        session,
                        level="INFO",
                        message={
                            "evt": "reserve_consume_skipped_no_wh_candidate",
                            "trace_id": trace.trace_id,
                            "platform": platform,
                            "ref": task["ref"],
                        },
                    )
                    reserve_used = False
                else:
                    for wid in wh_candidates:
                        try:
                            rsv_result = await soft_svc.pick_consume(
                                session,
                                platform=platform_db,
                                shop_id=task["shop_id"],
                                warehouse_id=int(wid),
                                ref=task["ref"],
                                occurred_at=occurred_at,
                                trace_id=trace.trace_id,
                            )
                            if rsv_result.get("status") == "CONSUMED":
                                reserve_used = True
                                await audit.write_json(
                                    session,
                                    level="INFO",
                                    message={
                                        "evt": "event_shipped_via_reserve",
                                        "trace_id": trace.trace_id,
                                        "platform": platform,
                                        "ref": task["ref"],
                                        "reservation_id": rsv_result.get("reservation_id"),
                                        "warehouse_id": int(wid),
                                        "warehouse_id_candidates": wh_candidates,
                                    },
                                )
                                break
                        except Exception as e:
                            await audit.write_json(
                                session,
                                level="WARN",
                                message={
                                    "evt": "reserve_consume_failed",
                                    "trace_id": trace.trace_id,
                                    "platform": platform,
                                    "ref": task["ref"],
                                    "warehouse_id": int(wid),
                                    "error": str(e),
                                },
                            )
                            continue

                # Step 2: reserve 未发挥作用 → 硬出库
                if not reserve_used:
                    svc = OutboundService()
                    await svc.commit(
                        session=session,
                        order_id=task["ref"],
                        lines=lines,
                        occurred_at=occurred_at,
                        warehouse_code=wh_code,
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
                            "lines": len(lines),
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
