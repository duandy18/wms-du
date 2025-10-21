from __future__ import annotations
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, text

from app.services.audit_logger import log_event
from app.services.platform_adapter import (
    PDDAdapter, TaobaoAdapter, TmallAdapter, JDAdapter, DouyinAdapter, XHSAdapter, PlatformAdapter
)
from app.models.event_error_log import EventErrorLog

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
    try:
        async with session.begin_nested():
            await session.execute(insert(EventErrorLog).values(
                platform=str(platform or ""),
                event_id=_extract_ref(raw),
                error_type=type(err).__name__,
                message=msg,
                payload=raw,
                shop_id=_extract_shop_id(raw),
            ))
    except Exception:
        # 保存点回滚即可，不触碰外层事务
        pass

async def _has_outbound_ledger(session: Optional[AsyncSession], ref: str) -> bool:
    if session is None:
        return True
    cnt = (await session.execute(
        text("SELECT COUNT(1) FROM stock_ledger WHERE reason='OUTBOUND' AND ref=:r"),
        {"r": ref},
    )).scalar_one()
    return (cnt or 0) > 0

async def handle_event_batch(
    events: List[Dict[str, Any]],
    session: Optional[AsyncSession] = None,
) -> None:
    """
    多平台事件批处理（无外层事务）：
    - 每条事件开始前先 rollback 清理潜在 aborted/savepoint 残留
    - raw 自带 lines：先直接执行（最短路径）→ 验证 ledger，未落账再试一次
    - raw 不带 lines：走适配器 parse→map，执行后同样验证，未落账再试一次
    """
    from app.services.outbound_service import OutboundService

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

            # 情况 A：raw 自带 lines，先跑最短路径
            if isinstance(raw_lines, list) and raw_lines:
                task_raw = {
                    "platform": platform,
                    "ref": ref_raw,
                    "state": state_raw,
                    "lines": raw_lines,
                    "shop_id": shop_id,
                    "payload": raw,
                }
                await OutboundService.apply_event(task_raw, session=session)
                log_event("event_processed_raw", f"{platform}:{ref_raw}",
                          extra={"platform": platform, "ref": ref_raw, "state": state_raw, "shop_id": shop_id, "has_lines": True})
                if not await _has_outbound_ledger(session, f"{shop_id}:{ref_raw}" if shop_id else ref_raw):
                    await OutboundService.apply_event(task_raw, session=session)
                    log_event("event_processed_raw_retry", f"{platform}:{ref_raw}",
                              extra={"platform": platform, "ref": ref_raw, "retry": True})
                continue

            # 情况 B：raw 不带 lines → 走适配器
            adapter = _get_adapter(platform)
            parsed = await adapter.parse_event(raw)
            mapped = await adapter.to_outbound_task(parsed)

            task = {
                "platform": platform,
                "ref": mapped.get("ref") or ref_raw,
                "state": mapped.get("state") or state_raw,
                "lines": mapped.get("lines"),
                "shop_id": mapped.get("shop_id") or shop_id,
                "payload": mapped.get("payload") or raw,
            }
            await OutboundService.apply_event(task, session=session)
            log_event("event_processed_mapped", f"{platform}:{task.get('ref')}",
                      extra={"platform": platform, "ref": task.get("ref"), "state": task.get("state"),
                             "shop_id": task.get("shop_id"), "has_lines": bool(task.get("lines"))})
            if task.get("lines") and (not await _has_outbound_ledger(session, f"{task.get('shop_id') or ''}:{task.get('ref') or ''}".strip(":"))):
                await OutboundService.apply_event(task, session=session)
                log_event("event_processed_mapped_retry", f"{platform}:{task.get('ref')}",
                          extra={"platform": platform, "ref": task.get("ref"), "retry": True})

        except Exception as e:
            log_event("event_error", f"{platform}: {e}", extra={"raw": raw})
            if session is not None:
                await _log_error_isolated(session, platform, raw, e)
