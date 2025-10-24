# app/services/platform_events.py
from __future__ import annotations
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, text

from app.services.audit_logger import log_event
from app.services.platform_adapter import (
    PDDAdapter, TaobaoAdapter, TmallAdapter, JDAdapter, DouyinAdapter, XHSAdapter, PlatformAdapter
)
from app.models.event_error_log import EventErrorLog
from app.metrics import EVENTS, ERRS  # ← 指标：事件/错误

# ---------------- 状态机合法过渡（新增：允许 from_state 为 None 的初始流转） ----------------

# 明确的合法过渡表（可按业务继续扩展）
LEGAL_TRANSITIONS: dict[str, list[str]] = {
    "PAID": ["ALLOCATED", "CANCELED", "VOID"],
    "ALLOCATED": ["SHIPPED", "CANCELED", "VOID"],
    "SHIPPED": ["COMPLETED", "CANCELED", "VOID"],
}

# 首次落地时允许的初始目标态（from_state 为 None/""/"UNKNOWN"）
INITIAL_ALLOWED: set[str] = {"PAID", "ALLOCATED"}

def assert_legal_transition(from_state: Optional[str], to_state: str) -> None:
    """
    校验状态机过渡合法性。
    - 允许 from_state 为 None/""/UNKNOWN 的“首次落地”进入 INITIAL_ALLOWED。
    - 其余走 LEGAL_TRANSITIONS。
    """
    f = (from_state or "").upper() or None
    t = (to_state or "").upper()

    if f is None or f in {"", "UNKNOWN"}:
        if t in INITIAL_ALLOWED:
            return
        raise ValueError("ILLEGAL_TRANSITION")

    if f not in LEGAL_TRANSITIONS:
        raise ValueError(f"ILLEGAL_TRANSITION: unknown from_state {f}")
    if t not in LEGAL_TRANSITIONS[f]:
        raise ValueError(f"ILLEGAL_TRANSITION: {f}->{t} not allowed")

# ---------------- 平台事件处理逻辑（保持原有语义） ----------------

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
        raw.get("order_sn") or raw.get("tid") or raw.get("orderId")
        or raw.get("order_id") or raw.get("id") or ""
    )

def _extract_state(raw: Dict[str, Any]) -> str:
    return str(
        raw.get("status") or raw.get("trade_status") or raw.get("orderStatus") or ""
    )

def _extract_shop_id(raw: Dict[str, Any]) -> str:
    return str(
        raw.get("shop_id") or raw.get("shop") or raw.get("store_id")
        or raw.get("seller_id") or raw.get("author_id") or raw.get("shopId") or ""
    )

async def _log_error_isolated(session: AsyncSession, platform: str, raw: Dict[str, Any], err: Exception) -> None:
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
                    idempotency_key=f"{platform}:{ref_raw}" if ref_raw else platform or "",
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
    if session is None:
        return True
    cnt = (await session.execute(
        text("SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"),
        {"r": ref},
    )).scalar_one()
    return (cnt or 0) > 0

def _inc_event_metric(platform: str, shop_id: str, state: str) -> None:
    st = (state or "").upper() or "UNKNOWN"
    EVENTS.labels((platform or "").lower(), shop_id or "", st).inc()

def _inc_error_metric(platform: str, shop_id: str, code: str) -> None:
    ERRS.labels((platform or "").lower(), shop_id or "", code or "ERROR").inc()

async def handle_event_batch(events: List[Dict[str, Any]], session: Optional[AsyncSession] = None) -> None:
    """
    批处理平台事件：
    - 若 raw 携带 lines，直接按出库任务执行；
    - 否则走平台适配器 parse→to_outbound_task；
    - 在执行前做一次“状态机合法过渡”校验（from_state 为空视为首次落地）。
    """
    from app.services.outbound_service import OutboundService  # 延迟导入，避免循环依赖

    for raw in events:
        platform = str(raw.get("platform") or "").lower()
        try:
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    pass

            ref_raw    = _extract_ref(raw)
            state_raw  = _extract_state(raw)
            shop_id    = _extract_shop_id(raw)
            raw_lines  = raw.get("lines")

            # 允许 from_state 缺省（首次落地）
            from_state = (str(raw.get("from_state") or "").upper() or None)
            assert_legal_transition(from_state, state_raw or "PAID")

            # 情况 A：raw 自带 lines，先跑最短路径
            if isinstance(raw_lines, list) and raw_lines:
                task_raw = {
                    "platform": platform, "ref": ref_raw, "state": state_raw,
                    "lines": raw_lines, "shop_id": shop_id, "payload": raw,
                }
                await OutboundService.apply_event(task_raw, session=session)
                _inc_event_metric(platform, shop_id, state_raw)
                log_event("event_processed_raw", f"{platform}:{ref_raw}",
                          extra={"platform": platform, "ref": ref_raw, "state": state_raw, "shop_id": shop_id, "has_lines": True})
                if not await _has_outbound_ledger(session, f"{shop_id}:{ref_raw}" if shop_id else ref_raw):
                    await OutboundService.apply_event(task_raw, session=session)
                    _inc_event_metric(platform, shop_id, state_raw)
                    log_event("event_processed_raw_retry", f"{platform}:{ref_raw}",
                              extra={"platform": platform, "ref": ref_raw, "retry": True})
                continue

            # 情况 B：raw 不带 lines → 走适配器
            adapter = _get_adapter(platform)
            parsed = await adapter.parse_event(raw)
            mapped = await adapter.to_outbound_task(parsed)

            # 再做一次状态机校验（适配器映射后的 to_state）
            to_state = mapped.get("state") or state_raw
            assert_legal_transition(from_state, to_state or "PAID")

            task = {
                "platform": platform,
                "ref": mapped.get("ref") or ref_raw,
                "state": to_state,
                "lines": mapped.get("lines"),
                "shop_id": mapped.get("shop_id") or shop_id,
                "payload": mapped.get("payload") or raw,
            }
            await OutboundService.apply_event(task, session=session)
            _inc_event_metric(platform, task.get("shop_id") or "", task.get("state") or "")
            log_event("event_processed_mapped", f"{platform}:{task.get('ref')}",
                      extra={"platform": platform, "ref": task.get("ref"), "state": task.get("state"),
                             "shop_id": task.get("shop_id"), "has_lines": bool(task.get("lines"))})
            if task.get("lines") and (not await _has_outbound_ledger(session, f"{task.get('shop_id') or ''}:{task.get('ref') or ''}".strip(":"))):
                await OutboundService.apply_event(task, session=session)
                _inc_event_metric(platform, task.get("shop_id") or "", task.get("state") or "")
                log_event("event_processed_mapped_retry", f"{platform}:{task.get('ref')}",
                          extra={"platform": platform, "ref": task.get("ref"), "retry": True})

        except Exception as e:
            log_event("event_error", f"{platform}: {e}", extra={"raw": raw})
            _inc_error_metric(platform, _extract_shop_id(raw), type(e).__name__)
            if session is not None:
                await _log_error_isolated(session, platform, raw, e)
