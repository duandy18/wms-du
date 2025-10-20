# app/services/platform_events.py
from __future__ import annotations
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import insert, text

from app.services.audit_logger import log_event
from app.services.platform_adapter import (
    PDDAdapter, TaobaoAdapter, JDAdapter, PlatformAdapter
)
from app.models.event_error_log import EventErrorLog

# 适配器注册表
_ADAPTERS: Dict[str, PlatformAdapter] = {
    "pdd": PDDAdapter(),
    "taobao": TaobaoAdapter(),
    "jd": JDAdapter(),
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

async def _log_error_isolated(session: AsyncSession, platform: str, raw: Dict[str, Any], err: Exception) -> None:
    """错误落库（保存点内），不污染外层事务。"""
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
            ))
    except Exception:
        # 保存点回滚即可，不触碰外层事务
        pass

async def _has_outbound_ledger(session: Optional[AsyncSession], ref: str) -> bool:
    """检查该 ref 是否已经有一条 OUTBOUND 记账（幂等观测）。"""
    if session is None:
        return True  # 无会话不做检查
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
    - 每条事件开始前，若提供 session，先 rollback 一次清理潜在 aborted/savepoint 残留
    - raw 自带 lines：先直接执行（最短路径），随后验证 ledger；未落账则再执行一次（幂等吸收）
    - raw 不带 lines：走适配器 parse→map；执行后同样验证 ledger，不落账再试一次
    - 错单落库用保存点，避免污染会话
    """
    from app.services.outbound_service import OutboundService

    for raw in events:
        platform = str(raw.get("platform") or "").lower()
        try:
            # 0) 清理潜在的 aborted/savepoint 残留，保证本条事件有干净起点
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    pass

            ref_raw   = _extract_ref(raw)
            state_raw = _extract_state(raw)
            raw_lines = raw.get("lines")

            # === 情况 A：raw 自带 lines，先跑最短路径 ===
            if isinstance(raw_lines, list) and raw_lines:
                task_raw = {
                    "platform": platform,
                    "ref": ref_raw,
                    "state": state_raw,
                    "lines": raw_lines,
                    "payload": raw,
                }
                await OutboundService.apply_event(task_raw, session=session)
                log_event("event_processed_raw",
                          f"{platform}:{ref_raw}",
                          extra={"platform": platform, "ref": ref_raw, "state": state_raw, "has_lines": True})

                # 验证兜底：若仍未落账，再试一次（幂等吸收）
                if not await _has_outbound_ledger(session, ref_raw):
                    await OutboundService.apply_event(task_raw, session=session)
                    log_event("event_processed_raw_retry",
                              f"{platform}:{ref_raw}",
                              extra={"platform": platform, "ref": ref_raw, "retry": True})
                # 本条事件处理完毕
                continue

            # === 情况 B：raw 不带 lines，走适配器映射 ===
            adapter = _get_adapter(platform)
            parsed = await adapter.parse_event(raw)
            task = await adapter.to_outbound_task(parsed)

            # 保底：若适配器没给 ref/state，尝试从 raw 提取
            task.setdefault("platform", platform)
            task.setdefault("ref",   ref_raw)
            task.setdefault("state", state_raw)

            await OutboundService.apply_event(task, session=session)
            log_event("event_processed_mapped",
                      f"{platform}:{task.get('ref')}",
                      extra={"platform": platform, "ref": task.get("ref"),
                             "state": task.get("state"), "has_lines": bool(task.get("lines"))})

            # 验证兜底：若任务包含 lines 仍未落账，再试一次
            if task.get("lines") and (not await _has_outbound_ledger(session, task.get("ref") or "")):
                await OutboundService.apply_event(task, session=session)
                log_event("event_processed_mapped_retry",
                          f"{platform}:{task.get("ref")}",
                          extra={"platform": platform, "ref": task.get("ref"), "retry": True})

        except Exception as e:
            log_event("event_error", f"{platform}: {e}", extra={"raw": raw})
            if session is not None:
                await _log_error_isolated(session, platform, raw, e)
