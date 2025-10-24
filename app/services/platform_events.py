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
from app.metrics import EVENTS, ERRS  # 事件/错误指标

# ---------------- 状态机合法过渡（允许 from_state=None 的首次落地） ----------------

LEGAL_TRANSITIONS: dict[str, list[str]] = {
    "PAID": ["ALLOCATED", "CANCELED", "VOID"],
    "ALLOCATED": ["SHIPPED", "CANCELED", "VOID"],
    "SHIPPED": ["COMPLETED", "CANCELED", "VOID"],
}
INITIAL_ALLOWED: set[str] = {"PAID", "ALLOCATED"}

def assert_legal_transition(from_state: Optional[str], to_state: str) -> None:
    f = (from_state or "").upper() or None
    t = (to_state or "").upper()
    if f is None:
        if t in INITIAL_ALLOWED:
            return
        raise ValueError("ILLEGAL_TRANSITION")
    if f not in LEGAL_TRANSITIONS:
        raise ValueError(f"ILLEGAL_TRANSITION: unknown from_state {f}")
    if t not in LEGAL_TRANSITIONS[f]:
        raise ValueError(f"ILLEGAL_TRANSITION: {f}->{t} not allowed")

# ---------------- 平台态 → 规范态（桥接层映射） ----------------

def _normalize_platform_state(platform: str, raw_state: str) -> str:
    """
    在桥接层将平台“原始态”规范化为内部态：
    - tmall/taobao: WAIT_SELLER_SEND_GOODS -> PAID
    - 其余平台保持原样（已是 PAID/ALLOCATED 等）
    """
    p = (platform or "").lower()
    s = (raw_state or "").upper()
    if p in {"tmall", "taobao"} and s == "WAIT_SELLER_SEND_GOODS":
        return "PAID"
    return s

# ---------------- 其余辅助 ----------------

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

# ---------------- 主流程 ----------------

async def handle_event_batch(events: List[Dict[str, Any]], session: Optional[AsyncSession] = None) -> None:
    """
    批处理平台事件：
      - 若 raw 携带 lines，先规范化状态（例如天猫 WAIT_SELLER_SEND_GOODS -> PAID）再校验/入库；
      - 否则走平台适配器 parse → to_outbound_task；
      - 失败写 error_log + 计数，不中断批处理。
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

            ref_raw   = _extract_ref(raw)
            state_raw = _extract_state(raw)
            shop_id   = _extract_shop_id(raw)
            raw_lines = raw.get("lines")

            # —— 情况 A：事件自带 lines，先规范化状态再校验/执行 —— #
            if isinstance(raw_lines, list) and raw_lines:
                to_norm = _normalize_platform_state(platform, state_raw)
                # 首次落地允许：None -> PAID/ALLOCATED
                assert_legal_transition(None, to_norm)

                task_raw = {
                    "platform": platform,
                    "ref": ref_raw,
                    "state": to_norm,            # ★ 用规范化后的状态
                    "lines": raw_lines,
                    "shop_id": shop_id,
                    "payload": raw,
                }
                await OutboundService.apply_event(task_raw, session=session)
                _inc_event_metric(platform, shop_id, to_norm)
                log_event("event_processed_raw", f"{platform}:{ref_raw}",
                          extra={"platform": platform, "ref": ref_raw, "state": to_norm,
                                 "shop_id": shop_id, "has_lines": True})

                eff_ref = f"{shop_id}:{ref_raw}" if shop_id else ref_raw
                if not await _has_outbound_ledger(session, eff_ref):
                    await OutboundService.apply_event(task_raw, session=session)
                    _inc_event_metric(platform, shop_id, to_norm)
                    log_event("event_processed_raw_retry", f"{platform}:{ref_raw}",
                              extra={"platform": platform, "ref": ref_raw, "retry": True})
                continue

            # —— 情况 B：无 lines，走适配器 —— #
            adapter = _get_adapter(platform)
            parsed = await adapter.parse_event(raw)
            mapped = await adapter.to_outbound_task(parsed)

            to_state = _normalize_platform_state(platform, mapped.get("state") or state_raw)
            assert_legal_transition(None, to_state)  # 首次落地

            task = {
                "platform": platform,
                "ref": mapped.get("ref") or ref_raw,
                "state": to_state,              # ★ 规范化状态
                "lines": mapped.get("lines"),
                "shop_id": mapped.get("shop_id") or shop_id,
                "payload": mapped.get("payload") or raw,
            }
            await OutboundService.apply_event(task, session=session)
            _inc_event_metric(platform, task.get("shop_id") or "", to_state)
            log_event("event_processed_mapped", f"{platform}:{task.get('ref')}",
                      extra={"platform": platform, "ref": task.get("ref"),
                             "state": to_state, "shop_id": task.get("shop_id"),
                             "has_lines": bool(task.get("lines"))})

            eff_ref2 = f"{task.get('shop_id') or ''}:{task.get('ref') or ''}".strip(":")
            if task.get("lines") and (not await _has_outbound_ledger(session, eff_ref2)):
                await OutboundService.apply_event(task, session=session)
                _inc_event_metric(platform, task.get("shop_id") or "", to_state)
                log_event("event_processed_mapped_retry", f"{platform}:{task.get('ref')}",
                          extra={"platform": platform, "ref": task.get("ref"), "retry": True})

        except Exception as e:
            _inc_error_metric(platform, _extract_shop_id(raw), type(e).__name__)
            log_event("event_error", f"{platform}: {e}", extra={"raw": raw})
            if session is not None:
                await _log_error_isolated(session, platform, raw, e)
