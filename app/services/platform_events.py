# app/services/platform_events.py
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import new_trace
from app.metrics import ERRS, EVENTS
from app.models.event_error_log import EventErrorLog
from app.services._event_writer import EventWriter
from app.services.order_service import OrderService
from app.services.outbound_service import OutboundService
from app.services.platform_adapter import (
    DouyinAdapter,
    JDAdapter,
    PDDAdapter,
    PlatformAdapter,
    TaobaoAdapter,
    TmallAdapter,
    XHSAdapter,
)
from app.services.soft_reserve_service import SoftReserveService
from app.services.store_service import StoreService

try:
    from app.models.warehouse import WarehouseCode
except Exception:

    class WarehouseCode:  # type: ignore
        MAIN = "MAIN"


_ADAPTERS: Dict[str, PlatformAdapter] = {
    "pdd": PDDAdapter(),
    "taobao": TaobaoAdapter(),
    "tmall": TmallAdapter(),
    "jd": JDAdapter(),
    "douyin": DouyinAdapter(),
    "xhs": XHSAdapter(),
}


def _get_adapter(platform: str) -> PlatformAdapter:
    ad = _ADAPTERS.get((platform or "").lower())
    if not ad:
        raise ValueError(f"Unsupported platform: {platform}")
    return ad


def _extract_ref(raw: Dict[str, Any]) -> str:
    return str(
        raw.get("order_sn")
        or raw.get("tid")
        or raw.get("orderId")
        or raw.get("order_id")
        or raw.get("id")
        or ""
    )


def _extract_state(raw: Dict[str, Any]) -> str:
    return str(raw.get("status") or raw.get("trade_status") or raw.get("orderStatus") or "")


def _extract_shop_id(raw: Dict[str, Any]) -> str:
    return str(
        raw.get("shop_id")
        or raw.get("shop")
        or raw.get("store_id")
        or raw.get("seller_id")
        or raw.get("author_id")
        or raw.get("shopId")
        or ""
    )


def _inc_event_metric(platform: str, shop_id: str, state: str) -> None:
    EVENTS.labels(
        (platform or "").lower(),
        shop_id or "",
        (state or "").upper() or "UNKNOWN",
    ).inc()


def _inc_error_metric(platform: str, shop_id: str, code: str) -> None:
    ERRS.labels(
        (platform or "").lower(),
        shop_id or "",
        code or "ERROR",
    ).inc()


async def _log_error_isolated(
    session: AsyncSession,
    platform: str,
    raw: Dict[str, Any],
    err: Exception,
) -> None:
    msg = str(err)
    if len(msg) > 240:
        msg = msg[:240] + "…"

    try:
        async with session.begin_nested():
            await session.execute(
                insert(EventErrorLog).values(
                    platform=str(platform or ""),
                    shop_id=_extract_shop_id(raw),
                    order_no=_extract_ref(raw),
                    idempotency_key=f"{platform}:{_extract_ref(raw)}",
                    from_state=None,
                    to_state=_extract_state(raw),
                    error_code=type(err).__name__,
                    error_msg=msg,
                    payload_json=raw,
                    retry_count=0,
                    max_retries=0,
                )
            )
    except Exception:
        # 不能因为记录 error_log 失败把原错误吞掉，这里只是不再抛二次错误
        pass


_PAID_ALIASES = {
    "PAID",
    "PAID_OK",
    "NEW",
    "CREATED",
    "WAIT_SELLER_SEND_GOODS",
}
_CANCEL_ALIASES = {
    "CANCELED",
    "CANCELLED",
    "VOID",
    "TRADE_CLOSED",
}
_SHIPPED_ALIASES = {
    "SHIPPED",
    "DELIVERED",
    "WAIT_BUYER_CONFIRM_GOODS",
    "TRADE_FINISHED",
}


def _classify(state: str) -> str:
    u = (state or "").upper()
    if u in _PAID_ALIASES:
        return "RESERVE"
    if u in _CANCEL_ALIASES:
        return "CANCEL"
    if u in _SHIPPED_ALIASES:
        return "SHIP"
    return "IGNORE"


def _merge_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    acc: Dict[tuple, int] = defaultdict(int)
    for x in lines:
        key = (
            int(x["item_id"]),
            int(x["warehouse_id"]),
            str(x["batch_code"]),
        )
        acc[key] += int(x["qty"])
    return [
        {
            "item_id": k[0],
            "warehouse_id": k[1],
            "batch_code": k[2],
            "qty": q,
        }
        for k, q in acc.items()
    ]


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
        trace = new_trace(f"platform:{platform}:{_extract_ref(raw) or _extract_state(raw)}")

        try:
            adapter = _get_adapter(platform)
            parsed = await adapter.parse_event(raw)
            mapped = await adapter.to_outbound_task(parsed)

            task = {
                "platform": platform,
                "shop_id": mapped.get("shop_id") or _extract_shop_id(raw),
                "ref": mapped.get("ref") or _extract_ref(raw),
                "state": mapped.get("state") or _extract_state(raw),
                "lines": mapped.get("lines") or raw.get("lines") or [],
                "payload": mapped.get("payload") or raw,
                "warehouse_code": (
                    mapped.get("warehouse_code") if isinstance(mapped, dict) else None
                ),
            }

            _inc_event_metric(platform, task["shop_id"] or "", task["state"] or "")
            await audit.write_json(
                session,
                level="INFO",
                message={
                    "evt": "event_in",
                    "trace_id": trace.trace_id,
                    "task": {k: task[k] for k in ("platform", "shop_id", "ref", "state")},
                },
            )

            action = _classify(task["state"])
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
                    {
                        "item_id": int(x["item_id"]),
                        "qty": int(x["qty"]),
                    }
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
                    {
                        "item_id": int(x["item_id"]),
                        "qty": int(x["qty"]),
                    }
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

                mapped_ship = mapped.get("ship_lines") if isinstance(mapped, dict) else None
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
                    if {
                        "item_id",
                        "warehouse_id",
                        "batch_code",
                        "qty",
                    }.issubset(x.keys())
                ]
                if not lines:
                    raise ValueError(
                        "No valid ship lines (need item_id, warehouse_id, batch_code, qty)"
                    )

                # 先按 (item,wh,batch) 合并，供 OutboundService 使用
                lines = _merge_lines(lines)

                occurred_at = datetime.now(timezone.utc)
                wh_code = str(
                    (mapped.get("warehouse_code") if isinstance(mapped, dict) else None)
                    or task.get("warehouse_code")
                    or getattr(WarehouseCode, "MAIN", "MAIN")
                )

                # Step 1: 先尝试消费 soft reserve（避免“软占用扣一次 / 出库再扣一次”）
                soft_svc = SoftReserveService()
                platform_db = platform.upper()

                # Phase 3.6：按店铺默认仓消费 reservation；若未绑定则回落到 1
                wh_for_reserve = await StoreService.resolve_default_warehouse_for_platform_shop(
                    session,
                    platform=platform_db,
                    shop_id=task["shop_id"],
                )
                if wh_for_reserve is None:
                    wh_for_reserve = 1

                reserve_used = False
                try:
                    rsv_result = await soft_svc.pick_consume(
                        session,
                        platform=platform_db,
                        shop_id=task["shop_id"],
                        warehouse_id=int(wh_for_reserve),
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
                            },
                        )
                except Exception as e:
                    # soft reserve 失败不影响硬出库，只记一笔 warning
                    await audit.write_json(
                        session,
                        level="WARN",
                        message={
                            "evt": "reserve_consume_failed",
                            "trace_id": trace.trace_id,
                            "platform": platform,
                            "ref": task["ref"],
                            "error": str(e),
                        },
                    )
                    reserve_used = False

                # Step 2: 若 soft reserve 没有发挥作用，则走硬出库
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
            _inc_error_metric(platform, _extract_shop_id(raw), type(e).__name__)
            if session is not None:
                await _log_error_isolated(session, platform, raw, e)
            raise
