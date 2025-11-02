# app/services/process_event.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_logger import log_event, log_event_db
from app.services.platform_events import handle_event_batch

logger = logging.getLogger("wmsdu.events")


@asynccontextmanager
async def _session_ctx(session: Optional[AsyncSession], app_state: Any) -> AsyncIterator[AsyncSession]:
    """
    会话获取策略：
    - 若传入了 session：直接使用（调用方负责事务与提交）
    - 否则从 app_state.async_sessionmaker 获取一个新会话（需要在 app.main 设置过）
    """
    if session is not None:
        yield session
        return

    maker = getattr(app_state, "async_sessionmaker", None)
    if maker is None:
        raise RuntimeError("No async_sessionmaker on app.state; set it in app.main")
    async with maker() as s:  # type: ignore[func-returns-value]
        yield s


async def process_platform_events(
    *,
    events: Iterable[dict],
    session: Optional[AsyncSession] = None,
    app_state: Any = None,
) -> None:
    """
    入口：处理多平台“原始事件”批次。
    - 先记审计：event_batch_received
    - 汇总交给 platform_events.handle_event_batch
    - 完成后记审计：event_batch_processed
    """
    evts = list(events or [])
    batch_size = len(evts)
    log_event("event_batch_received", f"size={batch_size}")

    async with _session_ctx(session, app_state) as s:
        try:
            await log_event_db(s, kind="event_batch_received", key=str(batch_size))
        except Exception:
            pass

        # 交给强契约的批处理（内部做了状态分类、reserve/cancel/ship 调用、落错与指标）
        await handle_event_batch(evts, session=s)

        try:
            await log_event_db(s, kind="event_batch_processed", key=str(batch_size))
        except Exception:
            pass

    log_event("event_batch_processed", f"size={batch_size}")
