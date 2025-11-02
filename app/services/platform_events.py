# app/services/platform_events.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import insert, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.metrics import ERRS, EVENTS  # 指标：事件/错误
from app.models.event_error_log import EventErrorLog
from app.services.audit_logger import log_event
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

# ---------------------------------------------------------------------
# 适配器注册(平台小写)
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
# 抽取字段(适配“原始”事件的兜底)
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
# 观测与落错
# ---------------------------------------------------------------------
def _inc_event_metric(platform: str, shop_id: str, state: str) -> None:
    st = (state or "").upper() or "UNKNOWN"
    EVENTS.labels((platform or "").lower(), shop_id or "", st).inc()


def _inc_error_metric(platform: str, shop_id: str, code: str) -> None:
    ERRS.labels((platform or "").lower(), shop_id or "", code or "ERROR").inc()


async def _log_error_isolated(
    session: AsyncSession, platform: str, raw: Dict[str, Any], err: Exception
) -> None:
    """
    与 EventErrorLog 模型对齐：order_no / error_code / error_msg / payload_json / shop_id …
    使用保存点，不污染外层事务；异常时静默吞掉。
    """
    msg = str(err)
    if len(msg) > 240:
        msg = msg[:240] + "…"

    ref_raw = _extract_ref(raw)
    state_raw = _extract_state(raw)
    shop_id = _extract_shop_id(raw)

    try:
        async with session.begin_nested():
            await session.execute(
                insert(EventErrorLog).values(
                    platform=str(platform or ""),
                    shop_id=shop_id,
                    order_no=ref_raw,
                    idempotency_key=f"{platform}:{ref_raw}" if ref_raw else (platform or ""),
                    from_state=None,
                    to_state=state_raw,
                    error_code=type(err).__name__,
                    error_msg=msg,
                    payload_json=raw,
                    retry_count=0,
                    max_retries=0,
                )
            )
    except Exception:
        pass


async def _has_outbound_ledger(session: Optional[AsyncSession], ref: str) -> bool:
    """
    校验是否已经写入 OUTBOUND 台账(防重复/兜底重试用)。
    约定 ref：优先使用 “{shop_id}:{ref}”，否则使用 ref 本身(与 Outbound 侧一致)。
    """
    if session is None:
        return True
    cnt = (
        await session.execute(
            text("SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"),
            {"r": ref},
        )
    ).scalar_one()
    return (cnt or 0) > 0


# ---------------------------------------------------------------------
# 状态 → 动作映射(v1.0 强契约)
#   - PAID/CREATED/NEW  -> reserve(+reserved)
# - CANCELED/VOID      -> cancel (-reserved)
# - SHIPPED/DELIVERED  -> ship    (扣减 stocks + 写台账 + 释放 reserved + 刷新 visible)
# 其它状态只记指标/日志，不抛错(例如平台自定义子状态)
# ---------------------------------------------------------------------
_PAID_ALIASES = {"PAID", "PAID_OK", "NEW", "CREATED", "WAIT_SELLER_SEND_GOODS"}
_CANCEL_ALIASES = {"CANCELED", "CANCELLED", "VOID", "TRADE_CLOSED"}
_SHIPPED_ALIASES = {"SHIPPED", "DELIVERED", "WAIT_BUYER_CONFIRM_GOODS", "TRADE_FINISHED"}


def _classify(state: str) -> str:
    u = (state or "").upper()
    if u in _PAID_ALIASES:
        return "RESERVE"
    if u in _CANCEL_ALIASES:
        return "CANCEL"
    if u in _SHIPPED_ALIASES:
        return "SHIP"
    return "IGNORE"


# ---------------------------------------------------------------------
# 统一处理入口
# ---------------------------------------------------------------------
async def handle_event_batch(
    events: List[Dict[str, Any]],
    session: Optional[AsyncSession] = None,
) -> None:
    """
    多平台事件批处理(无外层事务)：
    - 使用适配器解析/映射为标准任务 {platform, shop_id, ref, state, lines}
    - 按状态映射到 reserve/cancel/ship 三步流
    - 每条事件前先 rollback 清理潜在 savepoint 残留
    - 对发货类事件做一次 Ledger 落账校验，未落账再重试一次
    """
    for raw in events:
        platform = str(raw.get("platform") or "").lower()
        try:
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    pass

            # 通过适配器产出标准任务；若没有适配器，则用兜底抽取
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
            }

            # 指标：事件输入
            _inc_event_metric(platform, task["shop_id"] or "", task["state"] or "")

            action = _classify(task["state"])
            if action == "IGNORE":
                log_event(
                    "event_ignored", f"{platform}:{task['ref']}", extra={"state": task["state"]}
                )
                continue

            # RESERVE：下单占用(不动 stocks / 不写台账)
            if action == "RESERVE":
                if not task["ref"]:
                    raise ValueError("Missing ref for RESERVE")
                lines = [
                    {"item_id": int(x["item_id"]), "qty": int(x["qty"])}
                    for x in task["lines"] or []
                    if "item_id" in x and "qty" in x
                ]
                if not lines:
                    # 没有明细也允许走 reserve(常见平台“已付无明细”通知)
                    lines = [
                        {
                            "item_id": int(task["payload"].get("item_id", 0)),
                            "qty": int(task["payload"].get("qty", 0)),
                        }
                    ]
                await OrderService.reserve(
                    session,
                    platform=platform,
                    shop_id=task["shop_id"],
                    ref=task["ref"],
                    lines=lines,
                )
                log_event(
                    "event_reserved", f"{platform}:{task['ref']}", extra={"lines": len(lines)}
                )
                continue

            # CANCEL：取消占用
            if action == "CANCEL":
                if not task["ref"]:
                    raise ValueError("Missing ref for CANCEL")
                lines = [
                    {"item_id": int(x["item_id"]), "qty": int(x["qty"])}
                    for x in task["lines"] or []
                    if "item_id" in x and "qty" in x
                ]
                if not lines:
                    lines = [
                        {
                            "item_id": int(task["payload"].get("item_id", 0)),
                            "qty": int(task["payload"].get("qty", 0)),
                        }
                    ]
                await OrderService.cancel(
                    session,
                    platform=platform,
                    shop_id=task["shop_id"],
                    ref=task["ref"],
                    lines=lines,
                )
                log_event(
                    "event_canceled", f"{platform}:{task['ref']}", extra={"lines": len(lines)}
                )
                continue

            # SHIP：发货出库(扣减 stocks + 写台账 + 释放占用 + 刷新可见量)
            if action == "SHIP":
                if not task["ref"]:
                    raise ValueError("Missing ref for SHIP")
                lines = [
                    {
                        "item_id": int(x["item_id"]),
                        "location_id": int(x["location_id"]),
                        "qty": int(x["qty"]),
                    }
                    for x in (task["lines"] or [])
                    if {"item_id", "location_id", "qty"}.issubset(x.keys())
                ]
                if not lines:
                    # 适配器应保证 lines 完整；若出现缺字段，直接视为异常
                    raise ValueError("No valid ship lines")

                await OutboundService.commit(
                    session,
                    platform=platform,
                    shop_id=task["shop_id"],
                    ref=task["ref"],
                    lines=lines,
                    refresh_visible=True,
                )
                log_event("event_shipped", f"{platform}:{task['ref']}", extra={"lines": len(lines)})

                # 一次性校验 Ledger；未落账再重试一次
                ref_for_check = (
                    f"{task['shop_id']}:{task['ref']}" if task["shop_id"] else task["ref"]
                )
                if not await _has_outbound_ledger(session, ref_for_check):
                    await OutboundService.commit(
                        session,
                        platform=platform,
                        shop_id=task["shop_id"],
                        ref=task["ref"],
                        lines=lines,
                        refresh_visible=True,
                    )
                    log_event(
                        "event_shipped_retry", f"{platform}:{task['ref']}", extra={"retry": True}
                    )

        except Exception as e:
            log_event("event_error", f"{platform}: {e}", extra={"raw": raw})
            _inc_error_metric(platform, _extract_shop_id(raw), type(e).__name__)
            if session is not None:
                await _log_error_isolated(session, platform, raw, e)
