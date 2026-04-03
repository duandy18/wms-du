# app/tasks.py
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.domain.events_enums import EventState
from app.limits import ensure_bucket
from app.metrics import ERRS, EVENTS, LAT
from app.wms.outbound.services.outbound_commit_service import OutboundService
from app.worker import celery  # 导入项目里暴露的 Celery 实例


def _s(v: Optional[Any], default: str = "") -> str:
    return str(v) if v is not None else default


async def _process_one(
    session: AsyncSession,
    *,
    platform: str,
    shop_id: str,
    payload: Dict[str, Any],
) -> str:
    """
    单条事件处理：
      1) 解析关键信息
      2) 状态机守卫（非法跃迁→落表 + ERRS 计数 + 抛错）
      3) 业务推进（调用 OutboundService.apply_event）
      4) 成功路径：EVENTS / LAT 上报
    """
    p = _s(platform).lower()
    s = _s(shop_id)

    order_no: str = _s(payload.get("order_no") or payload.get("ref"))
    to_state: str = _s(
        payload.get("to_state") or payload.get("state") or EventState.PAID.value
    ).upper()

    # 1) 旧 event_gateway 已退场：当前任务直接进入业务推进
    await session.commit()

    # 2) 业务推进（示例：出库提交 / 记账；保持你项目原有实现）
    task = {
        "platform": p,
        "shop_id": s,
        "ref": order_no,
        "state": to_state,
        "lines": payload.get("lines"),
        "payload": payload,  # 按 OutboundService.apply_event 期望的键名传递
    }
    t0 = time.perf_counter()
    await OutboundService.apply_event(task, session=session)

    # 3) 成功指标
    EVENTS.labels(p, s, to_state).inc()
    LAT.labels(p, s, to_state).observe(time.perf_counter() - t0)
    return "OK"


@celery.task(name="wms.process_event")
def process_event(platform: str, shop_id: str, payload: Dict[str, Any]) -> str:
    """
    Celery 任务入口：
      - 按 (platform, shop_id) 做令牌桶限流
      - 打开异步会话执行 _process_one
      - 异常兜底：仅当异常不是 ILLEGAL_TRANSITION 才补记错误计数（避免与网关重复）
    """

    async def _runner() -> str:
        p = _s(platform).lower()
        s = _s(shop_id)

        async with async_session_maker() as session:  # type: AsyncSession
            # 限流（每店/每平台一桶；从 platform_shops.rate_limit_qps 读取，读取失败则回退为 5 QPS）
            bucket = await ensure_bucket(session, p, s)
            if not bucket.allow():
                ERRS.labels(p, s, "RATE_LIMITED").inc()
                return "RATE_LIMITED"

            try:
                result = await _process_one(session, platform=p, shop_id=s, payload=payload or {})
                # 容错式提交：若业务内已提交则 no-op；否则在此统一落库
                try:
                    await session.commit()
                except Exception:
                    pass
                return result
            except Exception as exc:
                code = str(getattr(exc, "code", None) or type(exc).__name__)
                msg = str((exc.args[0] if getattr(exc, "args", None) else "") or "")
                # 状态机已对 ILLEGAL_TRANSITION 记过一次，这里避免重复计数
                if not (
                    code == "ILLEGAL_TRANSITION"
                    or (code == "ValueError" and msg == "ILLEGAL_TRANSITION")
                ):
                    ERRS.labels(p, s, code).inc()
                try:
                    await session.rollback()
                except Exception:
                    pass
                raise

    return asyncio.run(_runner())
